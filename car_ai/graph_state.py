from typing import TypedDict, List

class GraphState(TypedDict):
    question: str
    question_type: str
    context: str
    answer: str
    confidence: float
    retrieved_docs: List[str]
    requires_followup: bool
