# main.py
from asrada_controller import AsradaHeadOrchestrator
import threading
import time
from car_obd.car_data import CarDataHistory
from car_obd.alert_checker import AlertChecker

import os
import warnings
import sys
import RPi.GPIO as GPIO

# 오디오 오류만 필터링
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = 'hide'

# 경고 무시
warnings.filterwarnings("ignore")

# ====================================
# OBD 설정
# ====================================
COLLECT_INTERVAL = 3
ALERT_CHECK_INTERVAL = 1
HISTORY_SIZE = 3
ESP_RECONNECT_INTERVAL = 10

USE_FAKE_OBD = False

# ====================================
# GPIO 버튼 설정 (라즈베리파이용)
# ====================================
BUTTON_PIN = 17  # GPIO17 (Physical pin 11)

GPIO.setmode(GPIO.BCM)
GPIO.setup(BUTTON_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)

# ====================================
# 전역 객체
# ====================================
if USE_FAKE_OBD:
    print("[INFO] 🎭 가상 OBD 모드로 시작합니다.")
    from car_obd.fake_obd_connector import FakeOBDConnector

    g_obd_connector = FakeOBDConnector(port="COM4", baudrate=115200)
else:
    print("[INFO] 🚗 실제 OBD 모드로 시작합니다.")
    from car_obd.obd_connector import OBDConnector

    g_obd_connector = OBDConnector(port="COM4", baudrate=115200)

g_car_history = CarDataHistory(max_size=HISTORY_SIZE)
g_alert_checker = AlertChecker()
g_esp = AsradaHeadOrchestrator(g_car_history, esp_ip="192.168.219.110", esp_port=1234)


# 🆕 중복 실행 방지 개선: controller 내부에서 관리하므로 제거
# (AsradaHeadOrchestrator._event_in_progress로 대체)

# ====================================
# OBD 데이터 수집 스레드
# ====================================
def obd_collection_thread():
    """OBD 데이터 수집 스레드"""
    print("[INFO] OBD collection thread started.")
    while True:
        try:
            if not g_obd_connector.is_connected():
                print("[WARN] Lost OBD connection. Reconnecting...")
                g_obd_connector.reconnect()
                time.sleep(ESP_RECONNECT_INTERVAL)
                continue

            start = time.time()

            snapshot = g_obd_connector.collect_data()
            g_car_history.add(snapshot)

            speed = snapshot.get_speed_value()
            rpm = snapshot.get_rpm_value()

            if USE_FAKE_OBD:
                prefix = "🎭 [FAKE]"
            else:
                prefix = "🚗 [REAL]"

            dtc_count = len(snapshot.dtc_list)
            dtc_info = f"DTC: {dtc_count}" if dtc_count > 0 else "No DTC"

            elapsed = time.time() - start
            time.sleep(max(0, COLLECT_INTERVAL - elapsed))

        except Exception as e:
            print(f"[ERROR] OBD collection error: {e}")
            time.sleep(ESP_RECONNECT_INTERVAL)


# ====================================
# 알림 모니터링 스레드
# ====================================
def alert_monitor_thread():
    """별도 스레드에서 실시간 알림 체크"""
    print("[INFO] Alert monitoring thread started.")

    while True:
        try:
            if not g_obd_connector.is_connected():
                time.sleep(ESP_RECONNECT_INTERVAL)
                continue

            time.sleep(ALERT_CHECK_INTERVAL)
            current = g_car_history.get_latest()
            if not current:
                continue

            previous = g_car_history.get_previous(1)

            alerts = g_alert_checker.check_all(current, previous)

            for alert in alerts:
                g_esp.speak(alert)
        except Exception as e:
            print(f"[ERROR] OBD alert_monitor error: {e}")
            time.sleep(ESP_RECONNECT_INTERVAL)


# ====================================
# ESP 버튼 콜백
# ====================================
def on_button(msg):
    """
    🆕 단순화된 버튼 핸들러
    중복 실행 방지는 controller 내부에서 처리
    """
    if msg == "BUTTON_PRESS":

        # 메인 스레드를 차단하지 않도록 별도 스레드에서 실행
        threading.Thread(
            target=g_esp.on_button_press_event,
            args=("full",),
            daemon=True
        ).start()

# ====================================
# GPIO 버튼 콜백
# ====================================
def gpio_button_callback(channel):
    print("[GPIO] Button pressed!")
    threading.Thread(
        target=g_esp.on_button_press_event,
        args=("full",),
        daemon=True
    ).start()


def main():
    global g_esp, g_obd_connector

    # GPIO 버튼 이벤트 추가
    GPIO.add_event_detect(
        BUTTON_PIN,
        GPIO.FALLING,
        callback=gpio_button_callback,
        bouncetime=200  # 채터링 방지
    )


    # ESP 초기화
    g_esp.button_callback = on_button
    esp_connected = False
    try:
        esp_connected = g_esp.connect()
        if esp_connected:
            g_esp.servo_set(2, 90)
            g_esp.speak("ESP 연결 성공!")
        else:
            g_esp.speak("ESP 초기 연결 실패")
    except Exception as e:
        g_esp.speak(f"Exception ESP 연결 실패: {e}")
        esp_connected = False

    # OBD 초기화
    try:
        if g_obd_connector.connect():
            if g_obd_connector.is_fake():
                g_esp.speak("Fake OBD 연결 성공!")
            else:
                g_esp.speak("OBD 연결 성공!")
        else:
            g_esp.speak("OBD 연결 실패.")

        obd_thread = threading.Thread(target=obd_collection_thread, daemon=True)
        obd_thread.start()
        alert_thread = threading.Thread(target=alert_monitor_thread, daemon=True)
        alert_thread.start()

    except Exception as e:
        g_esp.speak("OBD 연결 실패. Exception 발생")

    print("\n" + "=" * 60)
    print("입력 테스트: 질문 직접 입력 = STT 건너뛰기 모드")
    print("t 입력 시 STT 포함 전체 시퀀스")
    print("q 입력 시 종료")
    print("=" * 60 + "\n")

    try:
        while True:
            status_indicator = "🟢" if g_esp.is_connected() else "🔴"
            if not g_esp.is_connected():
                try:
                    esp_connected = g_esp.connect()
                    if esp_connected:
                        g_esp.servo_set(2, 90)
                        g_esp.speak("ESP 연결 성공")
                    else:
                        print("[WARN] ESP 초기 연결 실패")
                except Exception as e:
                    print(f"[WARN] ESP 연결 실패: {e}")

            line = input(f"{status_indicator} > ")

            if line.strip().lower() == "q":
                break

            if line.strip().lower() == "t":
                print("t 입력 - STT 포함 전체 시퀀스\n")
                threading.Thread(
                    target=g_esp.on_button_press_event,
                    args=("full",),
                    daemon=True
                ).start()
            else:
                print("질문 입력 → STT 생략 모드\n")
                threading.Thread(
                    target=g_esp.on_button_press_event,
                    args=("skip_stt", line),
                    daemon=True
                ).start()

    except KeyboardInterrupt:
        print("\n[INFO] 프로그램 종료")

    finally:
        if g_obd_connector:
            g_obd_connector.disconnect()
            print(f"[INFO] OBD 수집 종료 - 총 {g_car_history.size()}개 스냅샷")


if __name__ == "__main__":
    main()
