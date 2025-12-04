import speech_recognition as sr
import time
import threading

# 🔧 마이크 리소스 관리 개선
_mic_lock = threading.Lock()
_last_mic_release_time = 0


def listen():
    global _last_mic_release_time

    # 이전 마이크 사용 후 충분한 대기 시간 확보
    with _mic_lock:
        elapsed = time.time() - _last_mic_release_time
        if elapsed < 1.0:
            wait_time = 1.0 - elapsed
            print(f"🎤 마이크 리소스 대기 중... ({wait_time:.2f}초)")
            time.sleep(wait_time)

    # 매번 새로운 마이크 인스턴스 생성 (리소스 충돌 방지)
    recognizer = sr.Recognizer()

    try:
        # 🔧 with 블록 내에서 마이크 생성 및 사용
        with sr.Microphone() as source:
            print("🎙️ 주변 소음 조정 중...")
            recognizer.adjust_for_ambient_noise(source, duration=0.5)  # 1초 -> 0.5초로 단축

            print("🎙️ 말하세요...")
            audio = recognizer.listen(source, timeout=5, phrase_time_limit=10)

        # with 블록 벗어나면 자동으로 마이크 해제
        print("🧠 음성 인식 중...")
        result = recognizer.recognize_google(audio, language="ko-KR")
        print("🎧 인식 결과:", result)
        return result

    except sr.WaitTimeoutError:
        print("⏱️ 타임아웃: 음성이 감지되지 않았습니다.")
        return ""
    except sr.UnknownValueError:
        print("❓ 음성을 인식할 수 없습니다.")
        return ""
    except Exception as e:
        print(f"❌ STT 오류: {e}")
        return ""
    finally:
        # 마이크 해제 시간 기록
        with _mic_lock:
            _last_mic_release_time = time.time()

        # 리소스 정리를 위한 추가 대기
        time.sleep(0.3)


def listen_when_key_pressed():
    input("\n⌨ 아무 키나 누르면 말하기 시작합니다...\n")
    return listen()