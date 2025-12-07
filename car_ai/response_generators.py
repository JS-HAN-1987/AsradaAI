# response_generators.py
import threading
from my_tts import speak, stop_current_speech, force_stop_flag
import time
import re

# 전역 중단 플래그 (모든 LLM 응답에서 공유)
STOP_LLM_FLAG = threading.Event()

# ====== 안정적인 문장 종료 정규식 ======
# 숫자(3.14), 번호(1.), ..., 약어 등을 방해하지 않고
# 진짜 문장 끝만 잡는 패턴
SENTENCE_END_REGEX = re.compile(
    r'(?<!\.\.)(?<=[^.0-9])\.(?=\s|$)|[!?](?=\s|$)'
)


def log(msg):
    return
    # print(f"[DEBUG][response_generators][{threading.get_ident()}] {msg}")


# ---------------------------------------------
#  공용 문장 처리 함수
# ---------------------------------------------
def extract_sentences(buffer):
    """
    buffer에서 문장 끝 패턴을 찾아 sentence 리스트로 반환.
    남은 잔여 텍스트도 반환.
    """
    sentences = []

    while True:
        m = SENTENCE_END_REGEX.search(buffer)
        if not m:
            break

        end = m.end()
        sentence = buffer[:end].strip()
        if sentence:
            sentences.append(sentence)

        buffer = buffer[end:].lstrip()

    return sentences, buffer


def stop_all_llm():
    """모든 LLM 스트리밍을 중단"""
    STOP_LLM_FLAG.set()
    stop_current_speech()
    time.sleep(0.1)

def reset_llm_stop():
    """LLM 중단 플래그 초기화"""
    STOP_LLM_FLAG.clear()
    

# ========================================================
#  1) 차량 데이터 응답
# ========================================================
def generate_car_data_response(llm, question, context):
    log("generate_car_data_response() 호출됨")

    if not context:
        return "차량 데이터 없음."

    prompt = f"""
"데이터" 블록에는 차량의 실시간 센서 값이 포함되어 있다.
"질문"에 대해, "데이터" 안에서 답을 찾아 설명한다.
추측하거나 만들어내지 않는다.
답변을 길게하지 않는다.
데이터: {context}
질문: {question}
"""

    response_text = ""
    last_real_char_time = None

    # 중단 플래그 초기화
    STOP_LLM_FLAG.clear()

    # 중단 체크
    if STOP_LLM_FLAG.is_set():
        return "처리가 중단되었습니다."
    
    for chunk in llm.stream(prompt):
        # 중단 요청 체크
        if STOP_LLM_FLAG.is_set():
            log("🛑 LLM 응답 중단됨")
            return "처리가 중단되었습니다."
            
        now = time.time()

        if chunk.strip():
            response_text += chunk
            last_real_char_time = now

        # ---- 문장 단위 처리 (정규식 기반) ----
        sentences, response_text = extract_sentences(response_text)
        for s in sentences:
            # 중단 요청 체크
            if STOP_LLM_FLAG.is_set() or force_stop_flag.is_set():
                break
            speak(s)

        # 중단 요청 체크
        if STOP_LLM_FLAG.is_set() or force_stop_flag.is_set():
            break

        # ---- 일정 시간 동안 new chunk 없으면 강제 flush ----
        if last_real_char_time and (now - last_real_char_time > 1.0) and response_text.strip():
            if not STOP_LLM_FLAG.is_set() and not force_stop_flag.is_set():
                speak(response_text.strip())
            response_text = ""
            last_real_char_time = None

    # ---- 종료 후 잔여 텍스트 처리 ----
    if response_text.strip() and not STOP_LLM_FLAG.is_set() and not force_stop_flag.is_set():
        speak(response_text.strip())

    return ""

# ========================================================
#  2) 일반 텍스트 응답
# ========================================================
def generate_general_response(llm, question):
    print(f"[DEBUG][response_generators] generate_general_response() 호출됨")

    prompt = f"""
    질문: {question}
    """

    response_text = ""
    last_real_char_time = None

    print(f"[DEBUG][response_generators] LLM 스트리밍 호출 시작")

    # 중단 플래그 초기화
    STOP_LLM_FLAG.clear()

    # 중단 체크
    if STOP_LLM_FLAG.is_set():
        return "처리가 중단되었습니다."

    for chunk in llm.stream(prompt):
        # 중단 요청 체크
        if STOP_LLM_FLAG.is_set():
            log("🛑 LLM 응답 중단됨")
            return "처리가 중단되었습니다."
            
        now = time.time()

        if chunk.strip():
            response_text += chunk
            last_real_char_time = now

        sentences, response_text = extract_sentences(response_text)
        for s in sentences:
            # 중단 요청 체크
            if STOP_LLM_FLAG.is_set() or force_stop_flag.is_set():
                break
            speak(s)

        # 중단 요청 체크
        if STOP_LLM_FLAG.is_set() or force_stop_flag.is_set():
            break

        if last_real_char_time and (now - last_real_char_time > 1.0) and response_text.strip():
            if not STOP_LLM_FLAG.is_set() and not force_stop_flag.is_set():
                speak(response_text.strip())
            response_text = ""
            last_real_char_time = None

    if response_text.strip() and not STOP_LLM_FLAG.is_set() and not force_stop_flag.is_set():
        speak(response_text.strip())


# ========================================================
# 3) 제어 응답
# ========================================================
def generate_control_response(question):
    ret = f"'{question}' 명령은 현재 제어 불가하다."
    return ret
