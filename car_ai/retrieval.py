def retrieve_data(retriever, question: str):
    if not retriever:
        return "", [], 0.0

    docs = retriever.invoke(question)
    contents = [d.page_content for d in docs]
    context = "\n".join(contents)

    confidence = min(1.0, len(docs) * 0.33)
    return context, contents, confidence
