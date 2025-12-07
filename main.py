# main.py
from asrada_controller import AsradaHeadOrchestrator
import threading
import time
from car_obd.car_data import CarDataHistory
from car_obd.alert_checker import AlertChecker

import os
import warnings
import sys

# 오디오 오류만 필터링
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = 'hide'

# 경고 무시
warnings.filterwarnings("ignore")

# ====================================
# 설정
# ====================================
COLLECT_INTERVAL = 3
ALERT_CHECK_INTERVAL = 1
HISTORY_SIZE = 3
ESP_RECONNECT_INTERVAL = 10

USE_FAKE_OBD = True
USE_GPIO = True  # GPIO 사용 여부 (라즈베리파이에서는 True, Windows에서는 False로 설정)

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

    g_obd_connector = OBDConnector( )

g_car_history = CarDataHistory(max_size=HISTORY_SIZE)
g_alert_checker = AlertChecker()
g_esp = AsradaHeadOrchestrator(g_car_history, esp_hostname="esp8266-d3c2cf.local", esp_port=1234)

# ====================================
# GPIO 설정 (USE_GPIO가 True일 때만)
# ====================================
if USE_GPIO:
    try:
        import RPi.GPIO as GPIO
        BUTTON_PIN = 17
    except ImportError as e:
        print(f"[WARN] RPi.GPIO를 불러올 수 없습니다: {e}")
        print("[WARN] GPIO 기능을 비활성화합니다.")
        USE_GPIO = False
else:
    print("[INFO] GPIO 기능이 비활성화되었습니다.")


def init_gpio_button():
    """GPIO 버튼 초기화"""
    global USE_GPIO, BUTTON_PIN  # 전역 변수 선언
    if not USE_GPIO:
        print("[INFO] GPIO 비활성화 상태 - 버튼 초기화 건너뜀")
        return

    try:
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(BUTTON_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        print("[INFO] GPIO 버튼 폴링 방식으로 초기화 완료")
    except Exception as e:
        print(f"[ERROR] GPIO 초기화 오류: {e}")
        USE_GPIO = False


def gpio_button_polling_loop():
    """
    버튼 1->0 변화를 폴링 방식으로 감지
    """
    if not USE_GPIO:
        print("[INFO] GPIO 비활성화 상태 - 버튼 폴링 루프 종료")
        return

    try:
        last = GPIO.input(BUTTON_PIN)
    except Exception as e:
        print(f"[ERROR] GPIO 입력 읽기 실패: {e}")
        return

    while USE_GPIO:
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
    # GPIO 버튼 초기화 (활성화된 경우만)
    # -------------------------
    if USE_GPIO:
        print("[INFO] GPIO 버튼 초기화 시작...")
        init_gpio_button()

        # 버튼 폴링 스레드 시작
        threading.Thread(
            target=gpio_button_polling_loop,
            daemon=True
        ).start()
        print("[INFO] GPIO 버튼 폴링 스레드 시작됨")
    else:
        print("[INFO] GPIO 비활성화 - 버튼 기능 건너뜀")

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
    # GPIO 활성화 여부에 따른 메인 루프 분기
    # -------------------------
    if USE_GPIO:
        # GPIO 모드: 키보드 입력 없이 무한 대기
        print("\n" + "=" * 60)
        print("GPIO 모드: 키보드 입력 비활성화")
        print("ESP 버튼 또는 GPIO 버튼으로 동작")
        print("프로그램 종료: Ctrl+C")
        print("=" * 60 + "\n")

        try:
            # 무한 대기 (키보드 입력 없음)
            while True:
                # ESP 연결 상태 확인 및 재연결
                if not g_esp.is_connected():
                    try:
                        esp_connected = g_esp.connect()
                        if esp_connected:
                            g_esp.servo_set(2, 90)
                            print("[INFO] ESP 재연결 성공")
                    except Exception as e:
                        print(f"[WARN] ESP 연결 실패: {e}")

                # 상태 표시
                status = "🟢" if g_esp.is_connected() else "🔴"
                print(f"{status} ESP: {'연결됨' if g_esp.is_connected() else '연결끊김'} | ", end="")
                print(f"OBD: {'연결됨' if g_obd_connector.is_connected() else '연결끊김'}", end="\r")

                time.sleep(5)  # 5초마다 상태 체크

        except KeyboardInterrupt:
            print("\n[INFO] 프로그램 종료 (Ctrl+C)")

    else:
        # GPIO 비활성화 모드: 키보드 입력 활성화
        print("\n" + "=" * 60)
        print(f"시스템 상태: OBD={'가상' if USE_FAKE_OBD else '실제'}, GPIO={'활성화' if USE_GPIO else '비활성화'}")
        print("입력 테스트: 질문 직접 입력 = STT 건너뛰기 모드")
        print("t 입력 시 STT 포함 전체 시퀀스")
        print("c 입력 시 현재 진행 중인 이벤트 중단")
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

                line = input(f"{status_indicator} > ").strip()

                if line.lower() == "q":
                    break
                elif line.lower() == "c":
                    # 중단 명령
                    g_esp.cancel_current_event()
                    print("[MAIN] 현재 진행 중인 이벤트 중단 요청")
                elif line.lower() == "t":
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

        # ====================================
        # 종료 처리 (공통)
        # ====================================
        finally:
            # GPIO 정리 (활성화된 경우만)
            if USE_GPIO:
                try:
                    GPIO.cleanup()
                    print("[INFO] GPIO 정리 완료")
                except Exception as e:
                    print(f"[WARN] GPIO 정리 중 오류: {e}")

            # OBD 연결 종료
            if g_obd_connector:
                g_obd_connector.disconnect()
                print(f"[INFO] OBD 수집 종료 - 총 {g_car_history.size()}개 스냅샷")


if __name__ == "__main__":
    main()