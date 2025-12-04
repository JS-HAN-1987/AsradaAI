import os
import threading
import queue
import tempfile
import time
import pyaudio
from gtts import gTTS
from pydub import AudioSegment # pydub는 파일 로드에만 사용
import numpy as np
from typing import Optional, Tuple, Dict, Any

import os
os.environ["ALSA_LOG_LEVEL"] = "0"

# ====== 싱글톤 import (LED 제어용) ======
try:
    from asrada_head import head
except ImportError:
    class DummyHead:
        def send_led_level(self, level: int):
            pass
    head = DummyHead()
    print("⚠️ 'asrada_head' 모듈이 없어 더미 객체 사용")

# ====== 전역 변수 ======
audio_queue = queue.Queue()
is_running = True
stop_speech_flag = threading.Event()
current_audio_process = None
_audio_resource_lock = threading.Lock()
playback_start_event = threading.Event()
playback_start_time: Optional[float] = None
timing_results: Dict[str, Dict[str, float]] = {} 
current_sentence_key: Optional[str] = None 

# =======================================================
# 🌟 최적화 1: PyAudio 객체 전역 초기화 및 장치 인덱스 고정
# =======================================================
AUX_DEVICE_INDEX = 0 
GLOBAL_PYAUDIO: Optional[pyaudio.PyAudio] = None

try:
    GLOBAL_PYAUDIO = pyaudio.PyAudio()
    print(f"✅ PyAudio 전역 초기화 완료. 대상 장치 인덱스: {AUX_DEVICE_INDEX}")
except Exception as e:
    print(f"❌ PyAudio 전역 초기화 오류: {e}")
# =======================================================

# 🌟 음성 효과 관련 함수는 삭제함 (change_speed, shift_pitch, add_echo)

# ====== 오디오 처리 유틸리티 ======
# 🌟 최적화 2: 음성 효과 제거 및 직접 파일 사용
def create_robot_tts_file(text: str, speed: float = 1.4, pitch: float = -4.0,
                          echo_delay_ms: int = 70, echo_decay: float = 0.5) -> Tuple[str, Dict[str, float]]:
    """
    gTTS에서 받은 원본 파일을 그대로 사용하여 준비 시간을 최소화합니다.
    """
    timestamps: Dict[str, float] = {}
    start_time = time.perf_counter()
    
    # 1. gTTS API 호출 및 원본 저장
    # 🌟 임시 파일에 바로 MP3로 저장합니다.
    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as fp:
        final_path = fp.name
        tts = gTTS(text=text, lang="ko")
        tts.save(final_path)
    timestamps['tts_api_call_end'] = time.perf_counter()
    
    # 🌟 음성 효과 (pydub) 및 최종 파일 저장 단계가 제거됨

    timestamps['file_save_end'] = timestamps['tts_api_call_end']
    timestamps['total_prep_time'] = timestamps['file_save_end'] - start_time
    
    return final_path, timestamps

def create_beep_file(frequency: int = 880, duration_ms: int = 200) -> str:
    beep = Sine(frequency).to_audio_segment(duration=duration_ms) - 10
    beep = beep.fade_in(30).fade_out(30)
    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as fp:
        path = fp.name
        beep.export(path, format="mp3")
    return path

# ... (stop_current_speech 함수는 변경 없음) ...

# 🌟 play_and_monitor_sync 함수 수정: 상세 시간 기록
def play_and_monitor_sync(file_path: str, sound: AudioSegment):
    global stop_speech_flag, current_audio_process, playback_start_event, playback_start_time, timing_results, current_sentence_key

    if GLOBAL_PYAUDIO is None or current_sentence_key is None:
        print("❌ 재생 환경 준비 미흡 또는 문장 키 없음.")
        return

    # 🌟 파일 로딩 시간은 audio_worker에서 측정되었으므로 여기서는 0으로 간주

    with _audio_resource_lock:
        current_audio_process = "playing"
        if stop_speech_flag.is_set(): stop_speech_flag.clear()
        
        playback_start_time = time.perf_counter()
        playback_start_event.set()
        
        stream_open_start = time.perf_counter()
        stream = None
        try:
            stream = GLOBAL_PYAUDIO.open(format=GLOBAL_PYAUDIO.get_format_from_width(sound.sample_width),
                                         channels=sound.channels,
                                         rate=sound.frame_rate,
                                         output=True,
                                         output_device_index=AUX_DEVICE_INDEX)
            stream_open_end = time.perf_counter()
            timing_results[current_sentence_key]['stream_open_time'] = stream_open_end - stream_open_start

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

                # LED 레벨 계산 (변경 없음)
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
            
            timing_results[current_sentence_key]['playback_duration'] = time.perf_counter() - playback_start_time

        except Exception as e:
            print(f"❌ 재생 중 오류: {e}")

        finally:
            current_audio_process = None
            if stream: stream.stop_stream(); stream.close()
            head.send_led_level(0)
            stop_speech_flag.clear()
            playback_start_event.clear() 

# 🌟 audio_worker 함수 정의 (순서 수정)
def audio_worker():
    global is_running, current_sentence_key
    while is_running:
        try:
            item = audio_queue.get(timeout=0.5)
            if item is None: break
            
            file_path, sentence_key = item
            current_sentence_key = sentence_key

            if stop_speech_flag.is_set():
                if os.path.exists(file_path): os.remove(file_path)
                audio_queue.task_done()
                continue
            
            timing_results[sentence_key]['queue_wait_end_time'] = time.perf_counter()
            
            try:
                load_start = time.perf_counter()
                # 🌟 pydub는 파일 로드 및 디코딩에 사용
                sound = AudioSegment.from_mp3(file_path) 
                timing_results[sentence_key]['audio_load_time'] = time.perf_counter() - load_start
                
                play_and_monitor_sync(file_path, sound)
            except Exception as e:
                print(f"❌ 재생 오류: {e}")
            finally:
                if os.path.exists(file_path): os.remove(file_path)
                audio_queue.task_done()
                current_sentence_key = None 

        except queue.Empty:
            continue
        except Exception as e:
            print(f"❌ audio_worker 오류: {e}")
            time.sleep(0.1)

worker_thread = threading.Thread(target=audio_worker, daemon=True)
worker_thread.start()

# ... (play_beep 함수는 변경 없음) ...

# 🌟 stop_tts 함수 정의 (순서 수정)
def stop_tts():
    global is_running, GLOBAL_PYAUDIO
    print("🛑 TTS 스레드 종료 대기...")
    is_running = False
    stop_speech_flag.set()
    audio_queue.put(None) 
    worker_thread.join(timeout=2.0)
    
    if GLOBAL_PYAUDIO:
        try:
            GLOBAL_PYAUDIO.terminate()
            print("✅ PyAudio 객체 종료 완료")
        except Exception as e:
            print(f"❌ PyAudio 종료 중 오류: {e}")
            
    print("✅ TTS 시스템 종료 완료")

# ====== TTS 출력 ======
def speak(text: str, sentence_key: str, speed: float = 1.6, pitch: float = -4.0,
          echo_delay_ms: int = 70, echo_decay: float = 0.5) -> float:
    if not text: return 0.0
    print(f"🤖 {text}")
    try:
        global stop_speech_flag, timing_results
        if stop_speech_flag.is_set(): stop_speech_flag.clear()
        
        tts_path, prep_timestamps = create_robot_tts_file(text, speed, pitch, echo_delay_ms, echo_decay)
        
        timing_results[sentence_key] = prep_timestamps
        timing_results[sentence_key]['speak_call_time'] = time.perf_counter()

        if stop_speech_flag.is_set() and os.path.exists(tts_path): 
            os.remove(tts_path)
            return 0.0
            
        audio_queue.put((tts_path, sentence_key))
        
        return prep_timestamps['total_prep_time']
        
    except Exception as e:
        print(f"❌ speak() 오류: {e}")
        return 0.0

# =======================================================
# ====== 메인 함수 (시간 측정 로직은 이전과 동일) ======
# =======================================================

def main():
    global playback_start_time, timing_results

    target_sentences = [
        "안녕하세요. 저는 인공지능 로봇입니다. 이 문장의 출력이 완료되는 데 걸린 시간을 측정하고 있습니다. 안녕하세요. 저는 인공지능 로봇입니다. 이 문장의 출력이 완료되는 데 걸린 시간을 측정하고 있습니다. 안녕하세요. 저는 인공지능 로봇입니다. 이 문장의 출력이 완료되는 데 걸린 시간을 측정하고 있습니다. 안녕하세요. 저는 인공지능 로봇입니다. 이 문장의 출력이 완료되는 데 걸린 시간을 측정하고 있습니다."
    ]
    
    total_start_time = time.perf_counter()
    
    print("-" * 50)
    print("⭐ TTS 상세 시간 측정 시작 (최적화 모드)")
    print("-" * 50)

    for i, text in enumerate(target_sentences):
        sentence_key = f"Sentence_{i+1}"
        playback_start_time = None 
        playback_start_event.clear()

        print(f"[{i+1}/{len(target_sentences)}] 텍스트 처리 시작: '{text}'")
        
        speak_start_time = time.perf_counter()
        preparation_time = speak(text, sentence_key) 
        file_ready_time = time.perf_counter() 
        
        playback_start_event.wait(timeout=5) 
        speaker_start_time = playback_start_time
        if speaker_start_time is None:
            print("⚠️ 스피커 출력 시작 시간 측정 실패 (Time out 또는 오류).")
            speaker_start_time = file_ready_time 
        
        audio_queue.join()
        speaker_end_time = time.perf_counter()

        # 4. 결과 출력 및 상세 시간 분석
        
        time_text_input = file_ready_time - total_start_time
        time_speaker_start = speaker_start_time - total_start_time
        time_speaker_end = speaker_end_time - total_start_time
        
        prep_times = timing_results.get(sentence_key, {})
        tts_api_duration = prep_times.get('tts_api_call_end', speak_start_time) - speak_start_time
        
        queue_wait_end_time = prep_times.get('queue_wait_end_time', time_speaker_start)
        queue_wait_duration = queue_wait_end_time - file_ready_time
        
        audio_load_duration = prep_times.get('audio_load_time', 0)
        stream_open_duration = prep_times.get('stream_open_time', 0)
        
        print(f"✅ 문장 '{text}' 처리 완료")
        print(f"  - 전체 준비/재생 시간: {time_speaker_end:.4f} 초")
        print(f"  - 텍스트 입력/파일 생성 완료 시점: {time_text_input:.4f} 초")
        print(f"  - 스피커 출력 시작 시점: {time_speaker_start:.4f} 초")
        
        print("\n  --- 🔎 TTS 준비 상세 분석 (0.00s 부터) ---")
        print(f"  1. gTTS API 호출 및 최종 파일 저장: {tts_api_duration:.4f} 초")
        print(f"  ➡️ 총 준비 시간: {preparation_time:.4f} 초")
        
        print("\n  --- 🔎 재생 대기/시작 상세 분석 ---")
        print(f"  2. 큐 대기 시간 (파일 생성 완료 후): {queue_wait_duration:.4f} 초")
        print(f"  3. 파일 로드 및 스트림 오픈: {audio_load_duration + stream_open_duration:.4f} 초")
        print(f"     (3-1) 파일 로드 (AudioSegment): {audio_load_duration:.4f} 초")
        print(f"     (3-2) PyAudio 스트림 열기: {stream_open_duration:.4f} 초")
        print("-" * 50)
        
    final_end_time = time.perf_counter()
    total_duration = final_end_time - total_start_time
    
    print(f"🎉 모든 텍스트 출력 완료")
    print(f"  - 전체 테스트 총 소요 시간: {total_duration:.4f} 초")
    print("-" * 50)

    stop_tts()

if __name__ == "__main__":
    main()
    


    
    
