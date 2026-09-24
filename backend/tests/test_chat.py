"""Chat behaviour: grounding, refusal, citations, sessions, multi-turn,
LLM failure handling and ownership isolation.

These exercise the real retriever and real ChromaDB. Only Ollama is stubbed.
"""

import io

import pytest

from app.rag.prompt import FALLBACK_MESSAGE


def _upload_and_index(client, admin_headers, content: bytes, filename: str, title: str,
                      department: str = "Academics"):
    response = client.post(
        "/admin/documents/upload",
        headers=admin_headers,
        files={"file": (filename, io.BytesIO(content), "application/pdf")},
        data={
            "title": title,
            "department": department,
            "document_type": "policy",
            "academic_year": "2025-26",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


@pytest.fixture
def indexed_corpus(client, admin_headers, sample_pdf_bytes, second_pdf_bytes, inline_processing):
    """Two real, fully indexed documents to retrieve against."""
    attendance = _upload_and_index(
        client, admin_headers, sample_pdf_bytes, "attendance_policy.pdf", "Attendance Policy"
    )
    fees = _upload_and_index(
        client,
        admin_headers,
        second_pdf_bytes,
        "fees_structure.pdf",
        "Fee Structure",
        department="Accounts",
    )
    return {"attendance": attendance, "fees": fees}


# --- authentication --------------------------------------------------------


def test_chat_requires_authentication(client):
    assert client.post("/chat", json={"message": "Hello"}).status_code == 401


def test_chat_rejects_an_empty_message(client, student_headers):
    response = client.post("/chat", json={"message": "   "}, headers=student_headers)
    assert response.status_code == 422


def test_chat_rejects_an_overlong_message(client, student_headers):
    response = client.post("/chat", json={"message": "a" * 5000}, headers=student_headers)
    assert response.status_code == 422


# --- no documents indexed --------------------------------------------------


def test_with_no_documents_every_question_is_refused(client, student_headers, stub_llm):
    stub = stub_llm("echo")
    response = client.post(
        "/chat",
        json={"message": "What is the minimum attendance requirement?"},
        headers=student_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["grounded"] is False
    assert body["assistant_message"]["content"] == FALLBACK_MESSAGE
    assert body["assistant_message"]["citations"] == []
    assert stub.calls == [], "the LLM must not be called when nothing was retrieved"


# --- relevant questions ----------------------------------------------------


def test_a_relevant_question_is_answered_from_the_documents_with_citations(
    client, student_headers, indexed_corpus, stub_llm
):
    stub = stub_llm("echo")
    response = client.post(
        "/chat",
        json={"message": "What is the minimum attendance percentage required?"},
        headers=student_headers,
    )
    assert response.status_code == 200
    body = response.json()

    assert body["grounded"] is True
    assert body["llm_used"] is True
    assert len(stub.calls) == 1

    assistant = body["assistant_message"]
    assert assistant["citations"], "a grounded answer must carry citations"
    assert assistant["top_similarity"] >= 0.30
    titles = {c["title"] for c in assistant["citations"]}
    assert "Attendance Policy" in titles


def test_the_llm_receives_the_retrieved_context(
    client, student_headers, indexed_corpus, stub_llm
):
    stub = stub_llm("echo")
    client.post(
        "/chat",
        json={"message": "What is the minimum attendance percentage required?"},
        headers=student_headers,
    )
    prompt = stub.calls[0]
    assert "75%" in prompt
    assert "Context (official college documents)" in prompt


def test_retrieval_selects_the_right_document_among_several(
    client, student_headers, indexed_corpus, stub_llm
):
    stub_llm("echo")
    response = client.post(
        "/chat",
        json={"message": "What is the penalty for paying fees late?"},
        headers=student_headers,
    )
    titles = {c["title"] for c in response.json()["assistant_message"]["citations"]}
    assert "Fee Structure" in titles


# --- irrelevant questions --------------------------------------------------


@pytest.mark.parametrize(
    "question",
    [
        "What is the capital of France?",
        "Who won the 2018 football world cup?",
        "Give me a recipe for chocolate cake.",
    ],
)
def test_out_of_scope_questions_are_refused_without_calling_the_llm(
    client, student_headers, indexed_corpus, stub_llm, question
):
    stub = stub_llm("echo")
    response = client.post("/chat", json={"message": question}, headers=student_headers)
    body = response.json()

    assert body["grounded"] is False, f"{question!r} should not be answered"
    assert body["assistant_message"]["content"] == FALLBACK_MESSAGE
    assert body["assistant_message"]["citations"] == []
    assert stub.calls == []


def test_a_model_refusal_is_not_counted_as_a_grounded_answer(
    client, student_headers, indexed_corpus, stub_llm
):
    """If the model decides the context is insufficient, we must not display
    sources that would imply the answer came from them, and the answer must
    not be recorded as document-backed."""
    stub_llm("refuse")
    body = client.post(
        "/chat",
        json={"message": "What is the minimum attendance percentage required?"},
        headers=student_headers,
    ).json()
    assert body["assistant_message"]["citations"] == []
    assert body["grounded"] is False
    assert body["assistant_message"]["content"] == FALLBACK_MESSAGE


def test_an_off_topic_question_after_an_on_topic_one_is_still_refused(
    client, student_headers, indexed_corpus, stub_llm
):
    """Regression: the previous question used to be folded into every new
    question's search, letting an unrelated question borrow its similarity."""
    stub = stub_llm("echo")
    first = client.post(
        "/chat",
        json={"message": "What is the minimum attendance percentage required?"},
        headers=student_headers,
    ).json()
    assert first["grounded"] is True

    second = client.post(
        "/chat",
        json={
            "message": "Who is the current chief minister of the state?",
            "session_id": first["session_id"],
        },
        headers=student_headers,
    ).json()
    assert second["grounded"] is False
    assert second["assistant_message"]["content"] == FALLBACK_MESSAGE
    assert len(stub.calls) == 1, "the LLM must not be called for the off-topic question"


def test_an_empty_model_response_falls_back(client, student_headers, indexed_corpus, stub_llm):
    stub_llm("empty")
    body = client.post(
        "/chat",
        json={"message": "What is the minimum attendance percentage required?"},
        headers=student_headers,
    ).json()
    assert body["assistant_message"]["content"] == FALLBACK_MESSAGE
    assert body["grounded"] is False


# --- Ollama failure --------------------------------------------------------


def test_when_ollama_is_down_the_retrieved_text_is_returned_not_an_error(
    client, student_headers, indexed_corpus, stub_llm
):
    stub_llm("down")
    response = client.post(
        "/chat",
        json={"message": "What is the minimum attendance percentage required?"},
        headers=student_headers,
    )
    assert response.status_code == 200
    body = response.json()

    assert body["llm_used"] is False
    assert body["degraded_reason"]
    assert body["assistant_message"]["citations"], "citations still come from retrieval"
    assert "75%" in body["assistant_message"]["content"], "document text is served verbatim"


def test_when_the_model_is_not_pulled_the_user_still_gets_the_documents(
    client, student_headers, indexed_corpus, stub_llm
):
    stub_llm("missing_model")
    body = client.post(
        "/chat",
        json={"message": "What is the minimum attendance percentage required?"},
        headers=student_headers,
    ).json()
    assert body["llm_used"] is False
    assert "not pulled" in body["degraded_reason"]


# --- sessions and history --------------------------------------------------


def test_chat_creates_a_session_and_titles_it_from_the_first_question(
    client, student_headers, indexed_corpus, stub_llm
):
    stub_llm("echo")
    body = client.post(
        "/chat",
        json={"message": "What is the minimum attendance percentage required?"},
        headers=student_headers,
    ).json()
    assert body["session_id"]
    assert body["session_title"].startswith("What is the minimum attendance")


def test_messages_accumulate_in_one_session(client, student_headers, indexed_corpus, stub_llm):
    stub_llm("echo")
    first = client.post(
        "/chat", json={"message": "What is the attendance rule?"}, headers=student_headers
    ).json()
    session_id = first["session_id"]

    client.post(
        "/chat",
        json={"message": "What about lab attendance?", "session_id": session_id},
        headers=student_headers,
    )

    detail = client.get(f"/chat/sessions/{session_id}", headers=student_headers).json()
    assert detail["message_count"] == 4  # two questions, two answers
    assert [m["role"] for m in detail["messages"]] == [
        "user",
        "assistant",
        "user",
        "assistant",
    ]


def test_multi_turn_context_reaches_the_prompt(
    client, student_headers, indexed_corpus, stub_llm
):
    stub = stub_llm("echo")
    first = client.post(
        "/chat", json={"message": "What is the attendance requirement?"}, headers=student_headers
    ).json()
    client.post(
        "/chat",
        json={"message": "What happens if I fall below it?", "session_id": first["session_id"]},
        headers=student_headers,
    )
    second_prompt = stub.calls[-1]
    assert "What is the attendance requirement?" in second_prompt


def test_listing_sessions_returns_counts_and_previews(
    client, student_headers, indexed_corpus, stub_llm
):
    stub_llm("echo")
    client.post(
        "/chat", json={"message": "What is the attendance rule?"}, headers=student_headers
    )
    sessions = client.get("/chat/sessions", headers=student_headers).json()
    assert len(sessions) == 1
    assert sessions[0]["message_count"] == 2
    assert "attendance" in sessions[0]["preview"].lower()


def test_sessions_can_be_searched_by_message_text(
    client, student_headers, indexed_corpus, stub_llm
):
    stub_llm("echo")
    client.post(
        "/chat", json={"message": "What is the attendance rule?"}, headers=student_headers
    )
    client.post("/chat", json={"message": "How do I pay my fees?"}, headers=student_headers)

    found = client.get("/chat/sessions?search=fees", headers=student_headers).json()
    assert len(found) == 1
    assert "fees" in found[0]["preview"].lower()


def test_creating_an_empty_session_explicitly(client, student_headers):
    response = client.post("/chat/sessions", json={"title": "Fees questions"}, headers=student_headers)
    assert response.status_code == 201
    assert response.json()["title"] == "Fees questions"


def test_deleting_a_session_removes_its_messages(
    client, student_headers, indexed_corpus, stub_llm
):
    stub_llm("echo")
    session_id = client.post(
        "/chat", json={"message": "What is the attendance rule?"}, headers=student_headers
    ).json()["session_id"]

    assert client.delete(f"/chat/sessions/{session_id}", headers=student_headers).status_code == 200
    assert client.get(f"/chat/sessions/{session_id}", headers=student_headers).status_code == 404
    assert client.get("/chat/sessions", headers=student_headers).json() == []


# --- ownership isolation ---------------------------------------------------


def test_a_student_cannot_read_another_students_session(
    client, student_headers, indexed_corpus, stub_llm
):
    stub_llm("echo")
    session_id = client.post(
        "/chat", json={"message": "What is the attendance rule?"}, headers=student_headers
    ).json()["session_id"]

    other = client.post(
        "/auth/register",
        json={"email": "other@college.edu", "full_name": "Other", "password": "Passw0rd123"},
    ).json()
    other_headers = {"Authorization": f"Bearer {other['access_token']}"}

    assert client.get(f"/chat/sessions/{session_id}", headers=other_headers).status_code == 404
    assert client.delete(f"/chat/sessions/{session_id}", headers=other_headers).status_code == 404


def test_posting_to_another_users_session_is_rejected(
    client, student_headers, indexed_corpus, stub_llm
):
    stub_llm("echo")
    session_id = client.post(
        "/chat", json={"message": "What is the attendance rule?"}, headers=student_headers
    ).json()["session_id"]

    other = client.post(
        "/auth/register",
        json={"email": "other2@college.edu", "full_name": "Other2", "password": "Passw0rd123"},
    ).json()
    other_headers = {"Authorization": f"Bearer {other['access_token']}"}

    response = client.post(
        "/chat",
        json={"message": "Show me that", "session_id": session_id},
        headers=other_headers,
    )
    assert response.status_code == 404
