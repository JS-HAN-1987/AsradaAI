import os
import threading
import queue
import tempfile
import time
import pyaudio
from gtts import gTTS
from pydub import AudioSegment
from pydub.generators import Sine
import numpy as np
from typing import Optional, Tuple, Dict, Any

# =======================================================
# 🌟 로깅 설정
# =======================================================
LOGGING_ENABLED = True  # 이 플래그를 False로 바꾸면 모든 로그 출력이 비활성화됩니다.

def log_info(message: str):
    """일반 정보 로그 출력."""
    if LOGGING_ENABLED:
        print(message)

def log_error(message: str):
    """오류 로그 출력."""
    # 오류 메시지는 로깅 여부와 관계없이 출력합니다.
    print(f"❌ {message}")

os.environ["ALSA_LOG_LEVEL"] = "0"

# ====== 싱글톤 import (LED 제어용) ======
try:
    from asrada_head import head
except ImportError:
    class DummyHead:
        def send_led_level(self, level: int):
            pass
    head = DummyHead()
    log_info("⚠️ 'asrada_head' 모듈이 없어 더미 객체 사용")

# ====== 전역 변수 ======
audio_queue = queue.Queue()
is_running = True
stop_speech_flag = threading.Event()
current_audio_process = None
_audio_resource_lock = threading.Lock()

# 🔔 영구 비프음 파일 경로 및 이름 (현재 폴더에 저장)
BEEP_FILE_NAME = "beep.wav"
BEEP_FILE_PATH: str = os.path.join(os.getcwd(), BEEP_FILE_NAME)

# =======================================================
# 🌟 PyAudio 전역 초기화 및 장치 인덱스 고정
# =======================================================
AUX_DEVICE_NAME = "Headphones"
GLOBAL_PYAUDIO: Optional[pyaudio.PyAudio] = None
AUX_DEVICE_INDEX: Optional[int] = None

def get_aux_device_index(p: pyaudio.PyAudio):
    """'Headphones' 장치를 찾아 인덱스를 반환합니다."""
    for i in range(p.get_device_count()):
        info = p.get_device_info_by_index(i)
        if info["maxOutputChannels"] > 0 and AUX_DEVICE_NAME in info["name"]:
            return i
    return None

try:
    GLOBAL_PYAUDIO = pyaudio.PyAudio()
    AUX_DEVICE_INDEX = get_aux_device_index(GLOBAL_PYAUDIO)
    if AUX_DEVICE_INDEX is not None:
        log_info(f"✅ PyAudio 전역 초기화 완료. 대상 장치 인덱스: {AUX_DEVICE_INDEX}")
    else:
        AUX_DEVICE_INDEX = 0 
        log_info(f"❌ AUX 출력 장치 '{AUX_DEVICE_NAME}'를 찾을 수 없음. 인덱스 {AUX_DEVICE_INDEX} 사용 시도.")
except Exception as e:
    log_error(f"PyAudio 전역 초기화 오류: {e}")
# =======================================================

# ====== 비프음 생성 유틸리티 (1회 실행용) ======

def _generate_beep_audio(frequency: int = 880, duration_ms: int = 200) -> Optional[AudioSegment]:
    """비프음에 해당하는 AudioSegment를 생성하여 반환합니다."""
    try:
        beep = Sine(frequency).to_audio_segment(duration=duration_ms) - 10
        beep = beep.fade_in(30).fade_out(30)
        return beep
    except NameError:
        log_error("Sine 제너레이터를 찾을 수 없습니다. 비프음 AudioSegment 생성 실패.")
        return None

def _setup_persistent_beep_file():
    """시스템 초기화 시 비프음 파일을 한 번 생성하여 BEEP_FILE_PATH에 저장하거나 로드합니다."""
    
    if os.path.exists(BEEP_FILE_PATH):
        log_info(f"✅ 기존 비프음 파일 로드 완료: {BEEP_FILE_PATH}")
        return

    log_info(f"🔊 비프음 파일이 없어 새로 생성 시작: {BEEP_FILE_PATH}")
    
    sound = _generate_beep_audio()
    if sound is None:
        log_error("영구 비프음 파일을 생성할 수 없습니다.")
        return

    try:
        # WAV로 저장하여 후에 pydub 로드 시 오버헤드를 줄입니다.
        sound.export(BEEP_FILE_PATH, format="wav")
        log_info(f"✅ 비프음 파일 생성 및 저장 완료.")
    except Exception as e:
        log_error(f"비프음 파일 저장 중 오류: {e}")

# 🔔 PyAudio 초기화 후, 영구 비프음 파일 설정 실행
_setup_persistent_beep_file()

# ====== 오디오 처리 유틸리티 (음성 효과 포함) ======
def change_speed(sound: AudioSegment, speed: float) -> AudioSegment:
    """음성 속도를 변경합니다."""
    if speed == 1.0: return sound
    altered = sound._spawn(sound.raw_data, overrides={"frame_rate": int(sound.frame_rate * speed)})
    return altered.set_frame_rate(sound.frame_rate)

def shift_pitch(sound: AudioSegment, semitones: float) -> AudioSegment:
    """음성 피치를 변경합니다 (반음 기준)."""
    if semitones == 0: return sound
    new_rate = int(sound.frame_rate * (2.0 ** (semitones / 12)))
    return sound._spawn(sound.raw_data, overrides={"frame_rate": new_rate}).set_frame_rate(sound.frame_rate)

def add_echo(sound: AudioSegment, delay_ms: int = 70, decay: float = 0.5) -> AudioSegment:
    """간단한 에코 효과를 추가합니다."""
    echo = AudioSegment.silent(duration=delay_ms) + sound - (1 - decay) * 10
    return sound.overlay(echo)

def create_robot_tts_file(text: str, speed: float = 1.4, pitch: float = -4.0,
                          echo_delay_ms: int = 70, echo_decay: float = 0.5) -> str:
    """gTTS를 사용하여 음성 파일을 생성하고 효과를 적용한 후 WAV 경로를 반환합니다."""

    # 1. gTTS로 MP3 생성 (네트워크 통신)
    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as fp:
        raw_path = fp.name
        tts = gTTS(text=text, lang="ko")
        tts.save(raw_path)

    # 2. pydub로 MP3 로드, 효과 적용
    sound = AudioSegment.from_mp3(raw_path)
    sound = change_speed(sound, speed)
    sound = shift_pitch(sound, pitch)
    sound = add_echo(sound, echo_delay_ms, echo_decay)
    
    # 3. 최종 파일을 WAV로 변환하여 저장
    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as fp2:
        final_path = fp2.name
        sound.export(final_path, format="wav")

    try: os.remove(raw_path)
    except: pass

    return final_path


def stop_current_speech():
    """현재 재생 중인 오디오를 즉시 중단하고 큐를 비웁니다."""
    global stop_speech_flag, current_audio_process
    if current_audio_process is None: return

    log_info("🛑 음성 중단 요청")
    stop_speech_flag.set()
    head.send_led_level(0)
    current_audio_process = None

    # 큐 비우기
    try:
        while True:
            item = audio_queue.get_nowait()
            if isinstance(item, str) and os.path.exists(item):
                os.remove(item)
            audio_queue.task_done()
    except queue.Empty: pass

    time.sleep(0.3)

def play_and_monitor_sync(file_path: str, sound: AudioSegment):
    """오디오 데이터를 재생하고 LED 레벨을 모니터링합니다."""
    global stop_speech_flag, current_audio_process

    if GLOBAL_PYAUDIO is None or AUX_DEVICE_INDEX is None:
        log_error("재생 환경 준비 미흡.")
        return

    with _audio_resource_lock:
        current_audio_process = "playing"
        if stop_speech_flag.is_set(): stop_speech_flag.clear()
        
        stream = None
        try:
            stream = GLOBAL_PYAUDIO.open(format=GLOBAL_PYAUDIO.get_format_from_width(sound.sample_width),
                                         channels=sound.channels,
                                         rate=sound.frame_rate,
                                         output=True,
                                         output_device_index=AUX_DEVICE_INDEX)

            sound_data = sound.raw_data
            num_frames = len(sound_data) // sound.frame_width
            CHUNK_SIZE = int(sound.frame_rate * 0.02)

            head.send_led_level(0)

            i = 0
            while i < num_frames and not stop_speech_flag.is_set():
                start_frame = i
                end_frame = min(i + CHUNK_SIZE, num_frames)
                chunk_data = sound_data[start_frame * sound.frame_width: end_frame * sound.frame_width]

                stream.write(chunk_data)

                # LED 레벨 계산
                chunk_segment = sound._spawn(chunk_data)
                samples = np.array(chunk_segment.get_array_of_samples()) / (2 ** 15)
                rms = np.sqrt(np.mean(samples ** 2)) if len(samples) > 0 else 0
                level_db = 20 * np.log10(rms) if rms > 0 else -100
                if level_db < -40: led_level = 0
                elif level_db < -30: led_level = 1
                elif level_db < -20: led_level = 2
                else: led_level = 3
                head.send_led_level(led_level)

                i = end_frame
        
        except Exception as e:
            log_error(f"재생 중 오류: {e}")

        finally:
            current_audio_process = None
            if stream: stream.stop_stream(); stream.close()
            head.send_led_level(0)
            stop_speech_flag.clear()

def audio_worker():
    """오디오 재생 큐를 처리하는 스레드 작업자입니다."""
    global is_running
    while is_running:
        try:
            # 큐에서 파일 경로를 가져옴 (timeout 0.5초)
            file_path = audio_queue.get(timeout=0.5)
            if file_path is None: break
            
            if stop_speech_flag.is_set():
                if os.path.exists(file_path): os.remove(file_path)
                audio_queue.task_done()
                continue
            
            try:
                sound = AudioSegment.from_file(file_path)
                play_and_monitor_sync(file_path, sound)
            except Exception as e:
                log_error(f"재생 오류: {e}")
            finally:
                # TTS 파일은 임시 파일이므로 재생 후 삭제합니다.
                if os.path.exists(file_path): os.remove(file_path)
                audio_queue.task_done()

        except queue.Empty:
            continue
        except Exception as e:
            log_error(f"audio_worker 오류: {e}")
            time.sleep(0.1)

worker_thread = threading.Thread(target=audio_worker, daemon=True)
worker_thread.start()

# ====== 비프음 재생 ======
def play_beep():
    """비동기적으로 미리 생성된 비프음 파일을 재생합니다."""
    
    if GLOBAL_PYAUDIO is None or AUX_DEVICE_INDEX is None:
        log_error("PyAudio가 초기화되지 않아 비프음 재생 불가.")
        return
    
    # 파일이 존재하는지 최종 확인
    if not os.path.exists(BEEP_FILE_PATH):
        log_error(f"비프음 파일({BEEP_FILE_NAME})이 없습니다. 초기화 오류를 확인하세요.")
        return

    try:
        # 영구 저장된 파일을 로드합니다.
        sound = AudioSegment.from_file(BEEP_FILE_PATH)
        with _audio_resource_lock:
            stream = GLOBAL_PYAUDIO.open(format=GLOBAL_PYAUDIO.get_format_from_width(sound.sample_width),
                                         channels=sound.channels,
                                         rate=sound.frame_rate,
                                         output=True,
                                         output_device_index=AUX_DEVICE_INDEX)
            stream.write(sound.raw_data)
            stream.stop_stream(); stream.close()
            
    except Exception as e:
        log_error(f"비프음 오류: {e}")

# ====== TTS 출력 ======
def speak(text: str, speed: float = 1.6, pitch: float = -4.0,
          echo_delay_ms: int = 70, echo_decay: float = 0.5) -> None:
    """텍스트를 음성으로 변환하여 재생 큐에 추가합니다."""
    if not text: return 
    log_info(f"🤖 {text}") 
    try:
        global stop_speech_flag
        if stop_speech_flag.is_set(): stop_speech_flag.clear()
        
        tts_path = create_robot_tts_file(text, speed, pitch, echo_delay_ms, echo_decay)
        
        if stop_speech_flag.is_set() and os.path.exists(tts_path): 
            os.remove(tts_path)
            return
            
        # 큐에 파일 경로만 추가
        audio_queue.put(tts_path)
        
    except Exception as e:
        log_error(f"speak() 오류: {e}")


# 🌟 stop_tts 함수
def stop_tts():
    """TTS 시스템을 안전하게 종료합니다."""
    global is_running, GLOBAL_PYAUDIO
    log_info("🛑 TTS 스레드 종료 대기...") 
    is_running = False
    stop_speech_flag.set()
    audio_queue.put(None) # worker_thread 종료 신호
    worker_thread.join(timeout=2.0)
    
    # 🔔 영구 비프음 파일은 유지하도록 수정됨 (삭제 로직 제거)
            
    if GLOBAL_PYAUDIO:
        try:
            GLOBAL_PYAUDIO.terminate()
            log_info("✅ PyAudio 객체 종료 완료") 
        except Exception as e:
            log_error(f"PyAudio 종료 중 오류: {e}")
            
    log_info("✅ TTS 시스템 종료 완료")