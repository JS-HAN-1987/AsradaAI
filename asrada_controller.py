# asrada_controller.py
import threading
import time
import socket
from collections import deque
import random

from asrada_head import head
from my_stt import listen
from my_tts import speak, stop_current_speech, play_beep  # 🆕 play_beep 추가
from car_ai.car_ai_system import CarAISystem


def log(msg):
    """디버그 로그 출력. 나중에 주석 처리/레벨 제어 용이"""
    #    print(f"[DEBUG][Orchestrator] {msg}")
    return


class AsradaHeadOrchestrator:
    """
    AsradaHead 이용한 전체 시퀀스 오케스트레이터.
    """

    def __init__(self, car_history, esp_ip, esp_port=1234):
        self.esp = head
        self.esp.set_config(esp_ip, esp_port)

        # servo2 초기 위치
        self.servo2_pos = 2

        # 버튼 이벤트 콜백
        self.button_callback = None
        self.esp.on_message = self._on_head_message

        # AI
        self.ai = CarAISystem(car_history)

        # 상태 보호
        self._lock = threading.RLock()

        # 🆕 이벤트 진행 상태 플래그
        self._event_in_progress = False
        self._event_lock = threading.Lock()

    def is_connected(self):
        """ESP 연결 상태 확인"""
        return self.esp.is_connected()

    def connect(self):
        try:
            success = self.esp.connect()
            if success:
                print("[Controller] ESP 연결 성공")
            else:
                print("[Controller] ESP 연결 실패")
            return success
        except Exception as e:
            print(f"[Controller] connect 오류: {e}")
            return False

    def reconnect(self):
        """ESP 재연결 시도"""
        print("[Controller] ESP 재연결 시도 중...")
        return self.connect()

    # ---------------------------
    # ESP 패킷 래퍼
    # ---------------------------
    def led_set(self, idx, on=True):
        try:
            return self.esp.led_set(idx, on)
        except Exception as e:
            print("LED 제어 오류:", e)
            return False

    def servo_set(self, idx, angle):
        try:
            return self.esp.servo_set(idx, angle)
        except Exception as e:
            print("SERVO 제어 오류:", e)
            return False

    def led_level_set(self, level):
        try:
            return self.esp.send_led_level(level)
        except Exception as e:
            print("LED 제어 오류:", e)
            return False

    # -------------------------------
    #  버튼 이벤트 리스너
    # -------------------------------
    def _on_head_message(self, msg):
        """head 소켓에서 수신된 문자열 처리"""

        if msg == "BUTTON_PRESS":
            if self.button_callback:
                self.button_callback("BUTTON_PRESS")

    # ---------------------------
    # servo1 패턴 (동기)
    # ---------------------------
    def _servo1_pattern(self, delay_between=0.6):
        """
        항상 동일한 패턴: 90 -> 0 -> 180 -> 90
        blocking (패턴 완료될 때까지 반환 안 함)
        """
        with self._lock:
            if not self.is_connected():
                print("[Controller] Servo1: 연결 안됨")
                return
            self.servo_set(3, 0)

    # ---------------------------
    # servo2 이동 규칙 (한 번만 이동)
    # ---------------------------
    def _servo2_move_once(self):
        with self._lock:
            if not self.is_connected():
                print("[Controller] Servo2: 연결 안됨")
                return

            if self.servo2_pos == 2:
                self.servo2_pos = 1
                pos = random.randint(30, 60)
                success = self.servo_set(2, pos)
            else:
                self.servo2_pos = 2
                pos = random.randint(120, 150)
                success = self.servo_set(2, pos)

    # ---------------------------
    # 버튼 누름 이벤트 핸들러 (메인 시퀀스)
    # ---------------------------
    def on_button_press_event(self, mode="full", external_text=None):
        # 🆕 이벤트 중복 실행 방지 (더 정확한 체크)
        with self._event_lock:
            if self._event_in_progress:
                print("⏸ 이벤트 처리 중 - 새 요청 무시")
                return  # 👉 완전 종료
            self._event_in_progress = True
            stop_current_speech()

        try:
            log(f"이벤트 시작 (mode={mode})")

            # === 1) 공통: LED4(대기/동작) ON ===
            self.led_set(4, True)
            log("LED4 ON → 대기 표시 시작")

            if mode == "full":
                # 🆕 비프음으로 사용자에게 신호
                # print("🔔 음성 입력 대기 신호")
                play_beep( )

                self.led_set(5, True)
                log("LED5 ON → 음성 입력 표시 시작")

                # 🆕 비프음 재생 후 짧은 대기
                time.sleep(0.3)
                try:
                    recognized_text = listen()
                    log(f"STT 인식 완료: {recognized_text}")
                except Exception as e:
                    log(f"STT 오류: {e}")
                    recognized_text = ""

                self.led_set(5, False)
                log("LED5 OFF → 음성 입력 표시 종료")

                if not recognized_text:
                    log("인식된 음성 없음")
                    speak("질문을 인식하지 못했습니다.")
                    self.led_set(4, False)
                    return

                log(f"인식된 질문: {recognized_text}")

            else:
                recognized_text = external_text
                log(f"직접 입력된 질문: {recognized_text}")

            # Servo 동작
            def servo_worker():
                log("servo_worker 시작")
                self._servo1_pattern()
                log("servo1_pattern 완료 1차")
                time.sleep(5)
                self._servo2_move_once()
                log("servo2_move_once 완료")
                time.sleep(2)
                self._servo1_pattern()
                log("servo1_pattern 완료 2차")

            servo_thread = threading.Thread(target=servo_worker, daemon=True)
            servo_thread.start()
            log("Servo 스레드 시작")

            # AI 처리
            try:
                log("AI 처리 시작")
                answer = self.ai.process_question(recognized_text)
                log(f"AI 처리 완료: {answer}")
            except Exception as e:
                log(f"AI 처리 오류: {e}")
                answer = "AI 처리 중 오류 발생. 올라마 llm 로그인이 되어 있는지를 확인하라."

            log("speak() 호출 시작")
            speak(answer)

            servo_thread.join(timeout=3)
            log("Servo 스레드 종료")

            # 마지막으로 LED4 끄기
            self.led_set(4, False)
            log("LED4 OFF → 대기 표시 종료")
            log("이벤트 완료")

        finally:
            # 🆕 이벤트 완료 후 플래그 해제
            with self._event_lock:
                self._event_in_progress = False
                log("이벤트 플래그 해제")

    def speak(self, text):
        speak(text)