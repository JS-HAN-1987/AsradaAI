import json

def fallback_keyword_classify(question: str):
    q = question.lower()

    control_kw = ["켜", "꺼", "잠금", "창문", "비상등"]
    data_kw = ["속도", "rpm", "온도", "상태", "연료"]

    if any(k in q for k in control_kw):
        return "car_control"
    if any(k in q for k in data_kw):
        return "car_data"
    return "general"


def classify_question(llm, question: str):
    prompt = f"""
다음 문장을 세 가지 중 하나로 분류:
1. car_control
2. car_data
3. general

질문: {question}

JSON 형태로 출력:
{{"type": "..."}}
"""

    try:
        res = llm.invoke(prompt)
        data = json.loads(res)
        if data["type"] in ["car_control", "car_data", "general"]:
            return data["type"]
        return fallback_keyword_classify(question)
    except:
        return fallback_keyword_classify(question)
