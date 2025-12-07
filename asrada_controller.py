# asrada_controller.py
import threading
import time
import socket
from collections import deque
import random

from asrada_head import head
from my_stt import listen
from my_tts import speak, stop_current_speech, play_beep, force_stop_flag, current_audio_process, is_tts_active
from car_ai.response_generators import stop_all_llm, reset_llm_stop, STOP_LLM_FLAG
from car_ai.car_ai_system import CarAISystem


def log(msg):
    """디버그 로그 출력. 나중에 주석 처리/레벨 제어 용이"""
    print(f"[DEBUG][Orchestrator] {msg}")


class AsradaHeadOrchestrator:
    """
    AsradaHead 이용한 전체 시퀀스 오케스트레이터.
    """

    def __init__(self, car_history, esp_hostname=None, esp_port=1234):
        self.esp = head
        if esp_hostname:
            self.esp.set_config(esp_hostname, esp_port)
        else:
            # 자동 발견 모드
            self.esp.set_config()  # 기본값 사용

        # servo2 초기 위치
        self.servo2_pos = 2

        # 버튼 이벤트 콜백
        self.button_callback = None
        self.esp.on_message = self._on_head_message

        # AI
        self.ai = CarAISystem(car_history)

        # 상태 보호
        self._lock = threading.RLock()

        # 이벤트 진행 상태 및 중단 관리
        self._event_in_progress = False
        self._event_lock = threading.Lock()
        self._cancel_requested = threading.Event()

        # 활성 스레드 추적
        self._active_threads = []
        self._active_threads_lock = threading.Lock()

        # 현재 진행 중인 AI 처리 스레드
        self._current_ai_thread = None

        # 채터링 방지
        self._last_event_start_time = 0

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
        if msg == "BUTTON_PRESS" and self.button_callback:
            self.button_callback("BUTTON_PRESS")

    # ---------------------------
    # servo1 패턴 (동기)
    # ---------------------------
    def _servo1_pattern(self, delay_between=0.6, cancel_flag=None):
        """
        항상 동일한 패턴: 90 -> 0 -> 180 -> 90
        취소 플래그 확인
        """
        with self._lock:
            if not self.is_connected():
                print("[Controller] Servo1: 연결 안됨")
                return

            # 중단 체크
            if cancel_flag and cancel_flag.is_set():
                print("[Controller] Servo1: 중단됨")
                return

            self.servo_set(3, 0)

    # ---------------------------
    # servo2 이동 규칙 (한 번만 이동)
    # ---------------------------
    def _servo2_move_once(self, cancel_flag=None):
        with self._lock:
            if not self.is_connected():
                print("[Controller] Servo2: 연결 안됨")
                return

            # 중단 체크
            if cancel_flag and cancel_flag.is_set():
                print("[Controller] Servo2: 중단됨")
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
    # 활성 스레드 관리
    # ---------------------------
    def _add_active_thread(self, thread):
        """활성 스레드 추가"""
        with self._active_threads_lock:
            self._active_threads.append(thread)
            # 데드 스레드 정리
            self._active_threads = [t for t in self._active_threads if t.is_alive()]

    def _cleanup_active_threads(self):
        """활성 스레드 정리"""
        with self._active_threads_lock:
            self._active_threads = [t for t in self._active_threads if t.is_alive()]

    def _stop_all_active_threads(self):
        """모든 활성 스레드 중단 시도"""
        with self._active_threads_lock:
            for thread in self._active_threads:
                if thread.is_alive():
                    # 스레드 강제 종료는 위험할 수 있으므로 플래그 설정만
                    pass
            self._active_threads.clear()

    # ---------------------------
    # 버튼 누름 이벤트 핸들러 (메인 시퀀스)
    # ---------------------------
    def on_button_press_event(self, mode="full", external_text=None):
        # 🆕 채터링 방지: 마지막 이벤트 시작 시간 기록
        current_time = time.time()
        time_since_last_event = current_time - self._last_event_start_time

        # 1초 이내의 중복 호출은 채터링으로 간주하고 무시
        if time_since_last_event < 1.0:
            print(f"[Controller] ⏱️ 채터링 방지: {time_since_last_event:.2f}초 전에 시작됨, 무시")
            return

        # 🆕 이벤트 시작 시간 기록
        self._last_event_start_time = current_time


        """현재 진행 중인 이벤트/TTS 강제 중단"""
        # 🆕 is_tts_active() 함수 사용
        tts_playing = False
        try:
            tts_playing = is_tts_active()
        except Exception as e:
            print(f"[DEBUG] is_tts_active 오류: {e}")
            # 백업: current_audio_process 직접 확인
            tts_playing = (current_audio_process is not None)

        print(f"[Controller] 상태: event_in_progress={self._event_in_progress}, tts_playing={tts_playing}")

        # 🆕 TTS만 재생 중이어도 중단 가능
        if self._event_in_progress or tts_playing:
            print("[Controller] 기존 이벤트 중단")
            self.cancel_current_event()
            return

        # 중단 플래그 초기화
        self._cancel_requested.clear()
        reset_llm_stop()
        force_stop_flag.clear()

        # 이벤트 시작
        with self._event_lock:
            self._event_in_progress = True
            self._cancel_requested.clear()

        # 현재 이벤트 스레드 저장
        current_thread = threading.current_thread()
        self._add_active_thread(current_thread)

        try:
            log(f"이벤트 시작 (mode={mode})")

            # === 1) 공통: LED4(대기/동작) ON ===
            self.led_set(4, True)
            log("LED4 ON → 대기 표시 시작")

            if mode == "full":
                # 중단 요청 체크
                if self._cancel_requested.is_set():
                    print("[Controller] 중단 요청으로 STT 취소")
                    self.led_set(4, False)
                    return

                # 비프음으로 사용자에게 신호
                play_beep()
                time.sleep(0.2)  # 짧은 대기

                # 중단 요청 체크
                if self._cancel_requested.is_set():
                    print("[Controller] 중단 요청으로 STT 취소")
                    self.led_set(4, False)
                    return

                self.led_set(5, True)
                log("LED5 ON → 음성 입력 표시 시작")

                try:
                    recognized_text = listen()
                    log(f"STT 인식 완료: {recognized_text}")
                except Exception as e:
                    log(f"STT 오류: {e}")
                    recognized_text = ""

                self.led_set(5, False)
                log("LED5 OFF → 음성 입력 표시 종료")

                # 중단 요청 체크
                if self._cancel_requested.is_set():
                    print("[Controller] 중단 요청으로 처리 취소")
                    self.led_set(4, False)
                    return

                if not recognized_text:
                    log("인식된 음성 없음")
                    speak("질문을 인식하지 못했습니다.")
                    self.led_set(4, False)
                    return

                log(f"인식된 질문: {recognized_text}")

            else:
                recognized_text = external_text
                log(f"직접 입력된 질문: {recognized_text}")

            # Servo 동작 (취소 가능하도록)
            def servo_worker(cancel_flag):
                log("servo_worker 시작")

                # 중단 체크
                if cancel_flag.is_set():
                    print("[Controller] Servo: 중단됨")
                    return

                self._servo1_pattern(cancel_flag=cancel_flag)
                log("servo1_pattern 완료 1차")

                # 중단 체크
                if cancel_flag.is_set():
                    print("[Controller] Servo: 중단됨")
                    return

                # 첫 번째 대기 시간을 더 짧게 나눠서 중단 체크 가능하게
                for i in range(10):  # 5초를 0.5초씩 10번으로 나눔
                    if cancel_flag.is_set():
                        print("[Controller] Servo: 대기 중 중단됨")
                        return
                    time.sleep(0.5)

                self._servo2_move_once(cancel_flag=cancel_flag)
                log("servo2_move_once 완료")

                if cancel_flag.is_set():
                    print("[Controller] Servo: 중단됨")
                    return

                # 두 번째 대기 시간도 나눔
                for i in range(4):  # 2초를 0.5초씩 4번으로 나눔
                    if cancel_flag.is_set():
                        print("[Controller] Servo: 대기 중 중단됨")
                        return
                    time.sleep(0.5)

                self._servo1_pattern(cancel_flag=cancel_flag)
                log("servo1_pattern 완료 2차")

            servo_thread = threading.Thread(
                target=servo_worker,
                args=(self._cancel_requested,),
                daemon=True
            )
            servo_thread.start()
            self._add_active_thread(servo_thread)
            log("Servo 스레드 시작")

            # AI 처리
            try:
                log("AI 처리 시작")
                # 중단 요청 체크
                if self._cancel_requested.is_set():
                    print("[Controller] 중단 요청으로 AI 처리 취소")
                    self.led_set(4, False)
                    return

                answer = self.ai.process_question(recognized_text)

                # 🆕 AI 처리 완료 후 중단 체크
                if self._cancel_requested.is_set() or STOP_LLM_FLAG.is_set():
                    print("[Controller] 중단 요청으로 응답 생략")
                    self.led_set(4, False)
                    return

                log(f"AI 처리 완료: {answer}")
            except Exception as e:
                # 🆕 중단 요청으로 인한 예외 처리
                if self._cancel_requested.is_set() or STOP_LLM_FLAG.is_set():
                    print("[Controller] 중단 요청으로 AI 처리 중단됨")
                    self.led_set(4, False)
                    return
                print(f"AI 처리 오류: {e}")
                answer = f"AI 처리 오류: {e}"

            log("speak() 호출 시작")
            # 중단 요청 체크
            if not self._cancel_requested.is_set():
                speak(answer)

            servo_thread.join(timeout=3)
            log("Servo 스레드 종료")

            # 마지막으로 LED4 끄기
            self.led_set(4, False)
            log("LED4 OFF → 대기 표시 종료")
            log("이벤트 완료")

        except Exception as e:
            print(f"[Controller] 이벤트 처리 중 오류: {e}")
        finally:
            # 이벤트 완료 후 정리
            with self._event_lock:
                self._event_in_progress = False
                self._cancel_requested.clear()

            self._cleanup_active_threads()
            self._current_ai_thread = None

            log("이벤트 플래그 해제 및 정리 완료")

    def cancel_current_event(self):
        """현재 진행 중인 이벤트/TTS 강제 중단"""
        # 🆕 is_tts_active() 함수 사용
        tts_playing = False
        try:
            tts_playing = is_tts_active()
        except Exception as e:
            print(f"[DEBUG] is_tts_active 오류: {e}")
            # 백업: current_audio_process 직접 확인
            tts_playing = (current_audio_process is not None)

        print(f"[Controller] 상태: event_in_progress={self._event_in_progress}, tts_playing={tts_playing}")

        # 🆕 TTS만 재생 중이어도 중단 가능
        if not self._event_in_progress and not tts_playing:
            print("⚠️ 중단할 이벤트/TTS가 없음")
            return

        print("[Controller] 🔴 진행 중인 이벤트/TTS 강제 중단")

        # 🆕 가장 먼저 중단 플래그 설정
        self._cancel_requested.set()
        STOP_LLM_FLAG.set()
        force_stop_flag.set()

        # 모든 AI 및 LLM 처리 중단
        stop_all_llm()

        # TTS 강제 중단
        stop_current_speech()

        # LED 끄기
        self.led_set(4, False)
        self.led_set(5, False)

        # 활성 스레드 정리
        self._stop_all_active_threads()

        # 이벤트 상태 초기화
        with self._event_lock:
            self._event_in_progress = False
            self._cancel_requested.clear()

        print("[Controller] 모든 작업 중단 완료")

    def speak(self, text):
        """TTS 발화 (기존 발화 중단 후 새로 시작)"""
        # 기존 발화 중단
        #force_stop_flag.set()
        #stop_current_speech()
        #time.sleep(0.1)
        #force_stop_flag.clear()

        # 새 발화 시작
        speak(text)