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

# ====================================
# GPIO 설정
# ====================================
BUTTON_PIN = 17

def init_gpio_button():
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(BUTTON_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    print("[INFO] GPIO 버튼 폴링 방식으로 초기화 완료")

def gpio_button_polling_loop():
    """
    버튼 1->0 변화를 폴링 방식으로 감지
    """
    last = GPIO.input(BUTTON_PIN)

    while True:
        try:
            cur = GPIO.input(BUTTON_PIN)

            if last == 1 and cur == 0:
                print("[GPIO] Button Press Detected")

                threading.Thread(
                    target=g_esp.on_button_press_event,
                    args=("full",),
                    daemon=True
                ).start()

                time.sleep(0.3)

            last = cur
            time.sleep(0.5)

        except Exception as e:
            print("[ERROR] GPIO Polling 오류:", e)
            time.sleep(0.5)

# ====================================
# OBD 스레드
# ====================================
def obd_collection_thread():
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

            elapsed = time.time() - start
            time.sleep(max(0, COLLECT_INTERVAL - elapsed))

        except Exception as e:
            print(f"[ERROR] OBD collection error: {e}")
            time.sleep(ESP_RECONNECT_INTERVAL)

# ====================================
# 알림 모니터
# ====================================
def alert_monitor_thread():
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
# ESP 버튼 (ESP 장치에서 오는 신호용)
# ====================================
def on_button(msg):
    if msg == "BUTTON_PRESS":
        threading.Thread(
            target=g_esp.on_button_press_event,
            args=("full",),
            daemon=True
        ).start()

# ====================================
# main()
# ====================================
def main():

    # -------------------------
    # GPIO 버튼 초기화
    # -------------------------
    print("[INFO] GPIO 버튼 초기화 시작...")
    init_gpio_button()

    # 버튼 폴링 스레드 시작
    threading.Thread(
        target=gpio_button_polling_loop,
        daemon=True
    ).start()
    print("[INFO] GPIO 버튼 폴링 스레드 시작됨")

    # -------------------------
    # ESP 초기화
    # -------------------------
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

    # -------------------------
    # OBD 초기화
    # -------------------------
    try:
        if g_obd_connector.connect():
            if g_obd_connector.is_fake():
                g_esp.speak("Fake OBD 연결 성공!")
            else:
                g_esp.speak("OBD 연결 성공!")
        else:
            g_esp.speak("OBD 연결 실패.")

        threading.Thread(target=obd_collection_thread, daemon=True).start()
        threading.Thread(target=alert_monitor_thread, daemon=True).start()

    except Exception as e:
        g_esp.speak("OBD 연결 실패. Exception 발생")

    # -------------------------
    # 입력 루프
    # -------------------------
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
                except Exception as e:
                    print(f"[WARN] ESP 연결 실패: {e}")

            line = input(f"{status_indicator} > ")

            if line.strip().lower() == "q":
                break

            if line.strip().lower() == "t":
                threading.Thread(
                    target=g_esp.on_button_press_event,
                    args=("full",),
                    daemon=True
                ).start()
            else:
                threading.Thread(
                    target=g_esp.on_button_press_event,
                    args=("skip_stt", line),
                    daemon=True
                ).start()

    except KeyboardInterrupt:
        print("\n[INFO] 프로그램 종료")

    finally:
        GPIO.cleanup()
        if g_obd_connector:
            g_obd_connector.disconnect()
            print(f"[INFO] OBD 수집 종료 - 총 {g_car_history.size()}개 스냅샷")


if __name__ == "__main__":
    main()
