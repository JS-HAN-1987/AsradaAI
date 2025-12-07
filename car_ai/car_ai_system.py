# car_ai_system.py

from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_community.llms import Ollama
from langchain_core.prompts import PromptTemplate
from langchain_core.documents import Document

from .graph_state import GraphState
from .classify import classify_question
from .retrieval import retrieve_data
from .response_generators import (
    generate_car_data_response,
    generate_control_response,
    generate_general_response,
    STOP_LLM_FLAG
)

import time


def log(msg):
    print(f"[DEBUG][CarAISystem] {msg}")


class CarAISystem:
    def __init__(self, car_history):
        """
        Args:
            car_history: CarDataHistory 객체 (실시간 OBD 데이터)
        """
        start_time = time.time()
        log("초기화 시작")

        self.car_history = car_history

        # 초기 더미 문서로 FAISS 초기화 (나중에 업데이트)
        dummy_docs = [Document(page_content="아직 차량 데이터가 없다.", metadata={"timestamp": "init"})]

        embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")
        self.embeddings = embeddings
        self.db = FAISS.from_documents(dummy_docs, embeddings)
        self.retriever = self.db.as_retriever(search_kwargs={"k": 3})
        log("FAISS DB 및 retriever 초기화 완료")

        self.llm = Ollama(
            model="gpt-oss:20b-cloud",
            system="""너는 차량 데이터 전문 분석 AI이다.
            한국어로 답변한다.
            경어체를 사용하지 않는다.
            불필요한 서론이나 결론 생략한다.
            각 문장은 반드시 마침표로 끝난다. 
        """
        )
        log(f"Ollama LLM 초기화 완료, 소요 시간: {time.time() - start_time:.3f}s")

    def _snapshot_to_document(self, snapshot) -> Document:
        """CarDataSnapshot → LangChain Document (센서값 소수점 1자리로 표시)"""

        def format_value(sensor):
            if sensor is None:
                return None
            if sensor.value is None:
                return None
            try:
                return f"{sensor.value:.1f}"
            except:
                return sensor.value

        fv = format_value

        # DTC 정보 처리
        dtc_text = "문제 없음"
        if snapshot.dtc_list:
            dtc_text = ", ".join([f"{d.code}({d.message})" for d in snapshot.dtc_list])

        content = (
            f"시간: {snapshot.timestamp}\n"
            f"속도: {fv(snapshot.speed)} km/h\n"
            f"RPM: {fv(snapshot.rpm)}\n"
            f"냉각수 온도: {fv(snapshot.coolant_temp)} °C\n"
            f"연료 잔량: {fv(snapshot.fuel_level)} %\n"
            f"스로틀 위치: {fv(snapshot.throttle_pos)} %\n"
            f"엔진 부하: {fv(snapshot.engine_load)} %\n"
            f"ELM 전압: {fv(snapshot.elm_voltage)} V\n"
            f"오일 온도: {fv(snapshot.oil_temp)} °C\n"
            f"MAF: {fv(snapshot.maf)} g/s\n"
            f"점화 타이밍: {fv(snapshot.timing_advance)} °\n"
            f"연료 분사량: {fv(snapshot.fuel_rate)} L/h\n"
            f"연료 압력: {fv(snapshot.fuel_pressure)} kPa\n"
            f"에탄올 비율: {fv(snapshot.ethanol_percent)} %\n"
            f"STFT1: {fv(snapshot.short_fuel_trim_1)} %\n"
            f"LTFT1: {fv(snapshot.long_fuel_trim_1)} %\n"
            f"STFT2: {fv(snapshot.short_fuel_trim_2)} %\n"
            f"LTFT2: {fv(snapshot.long_fuel_trim_2)} %\n"
            f"촉매 온도 B1S1: {fv(snapshot.catalyst_temp_b1s1)} °C\n"
            f"촉매 온도 B2S1: {fv(snapshot.catalyst_temp_b2s1)} °C\n"
            f"EGR 명령: {fv(snapshot.commanded_egr)} %\n"
            f"EGR 오류율: {fv(snapshot.egr_error)} %\n"
            f"증발가스 압력: {fv(snapshot.evap_vapor_pressure)} Pa\n"
            f"가속페달 위치 D: {fv(snapshot.accelerator_pos_d)} %\n"
            f"엔진 작동 시간: {fv(snapshot.run_time)} s\n"
            f"DTC 클리어 후 주행 거리: {fv(snapshot.distance_since_dtc_clear)} km\n"
            f"MIL 점등 상태 주행 거리: {fv(snapshot.distance_w_mil)} km\n"
            f"제어 모듈 전압: {fv(snapshot.control_module_voltage)} V\n"
            f"고장 코드(DTC): {dtc_text}\n"
        )

        return Document(
            page_content=content,
            metadata={
                "timestamp": snapshot.timestamp,
                "speed": fv(snapshot.speed),
                "rpm": fv(snapshot.rpm),
                "coolant_temp": fv(snapshot.coolant_temp),
                "fuel_level": fv(snapshot.fuel_level),
                "engine_load": fv(snapshot.engine_load),
                "throttle_pos": fv(snapshot.throttle_pos),
                "has_dtc": len(snapshot.dtc_list) > 0
            }
        )

    def update_vector_db(self):
        """car_history에서 최신 데이터를 가져와 벡터 DB 업데이트"""
        if self.car_history is None:
            log("car_history가 없어 벡터 DB 업데이트 스킵")
            return

        snapshots = self.car_history.get_all()
        if not snapshots:
            log("히스토리가 비어있어 벡터 DB 업데이트 스킵")
            return

        start_time = time.time()

        # 스냅샷을 Document로 변환
        docs = [self._snapshot_to_document(snapshot) for snapshot in snapshots]

        # FAISS DB 재생성
        self.db = FAISS.from_documents(docs, self.embeddings)
        self.retriever = self.db.as_retriever(search_kwargs={"k": 3})

        log(f"벡터 DB 업데이트 완료, 문서 수: {len(docs)}, 소요 시간: {time.time() - start_time:.3f}s")

    def process_question(self, question: str) -> str:
        start_total = time.time()
        log(f"process_question() 호출, question: {question}")

        # 🆕 시작 전 즉시 중단 체크
        if STOP_LLM_FLAG.is_set():
            log("처리 시작 전 중단됨")
            return "처리가 중단되었습니다."

        # 질문 처리 전 벡터 DB 업데이트 (최신 데이터 반영)
        self.update_vector_db()

        # 🆕 벡터 DB 업데이트 후 중단 체크
        if STOP_LLM_FLAG.is_set():
            log("벡터 DB 업데이트 후 중단됨")
            return "처리가 중단되었습니다."

        state = GraphState(
            question=question,
            question_type="",
            context="",
            answer="",
            confidence=0.0,
            retrieved_docs=[],
            requires_followup=False
        )

        # 1. 분류
        start_step = time.time()
        state["question_type"] = classify_question(self.llm, question)
        log(f"1. 분류 완료 question_type = {state['question_type']}, 소요 시간: {time.time() - start_step:.3f}s")

        # 🆕 분류 후 중단 체크
        if STOP_LLM_FLAG.is_set():
            log("분류 후 중단됨")
            return "처리가 중단되었습니다."

        # 2. 데이터 검색
        start_step = time.time()
        state["context"], state["retrieved_docs"], state["confidence"] = retrieve_data(self.retriever, question)
        log(f"2. 데이터 검색 완료, context 길이: {len(state['context'])}, confidence: {state['confidence']:.3f}, 소요 시간: {time.time() - start_step:.3f}s")

        # 🆕 검색 후 중단 체크
        if STOP_LLM_FLAG.is_set():
            log("검색 후 중단됨")
            return "처리가 중단되었습니다."

        # 3. 응답 생성
        start_step = time.time()
        try:
            if state["question_type"] == "car_control":
                state["answer"] = generate_control_response(question)
            elif state["question_type"] == "car_data":
                state["answer"] = generate_car_data_response(self.llm, question, state["context"])
            else:
                state["answer"] = generate_general_response(self.llm, question)
        except Exception as e:
            # 🆕 중단 요청으로 인한 예외 처리
            if STOP_LLM_FLAG.is_set():
                log("응답 생성 중 중단됨")
                return "처리가 중단되었습니다."
            log(f"응답 생성 오류: {e}")
            state["answer"] = f"응답 생성 오류: {e}"

        log(f"응답 생성 완료, 소요 시간: {time.time() - start_step:.3f}s")

        log(f"process_question 총 소요 시간: {time.time() - start_total:.3f}s")
        return state["answer"]
