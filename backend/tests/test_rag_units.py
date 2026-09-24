"""Unit tests for the RAG building blocks: cleaning, segmentation, chunking,
extraction, prompt construction and citation assembly."""

from pathlib import Path

import pytest

from app.rag.chunker import Chunk, chunk_pages
from app.rag.extractor import ExtractionError, PageText, extract_document, has_extractable_text
from app.rag.pipeline import _build_citations, _contextualize
from app.rag.prompt import FALLBACK_MESSAGE, build_prompt, format_context
from app.rag.retriever import RetrievedChunk
from app.rag.segmentation import sentence_tokenize, word_tokenize
from app.rag.text_cleaner import clean_text, get_stopwords, normalize_for_matching


# --- cleaning --------------------------------------------------------------


def test_clean_text_repairs_hyphenated_line_breaks():
    assert "examination" in clean_text("semester exami-\nnation schedule")


def test_clean_text_collapses_whitespace_and_newlines():
    cleaned = clean_text("Attendance   is\n\n75%.\tStrictly   enforced.")
    assert "  " not in cleaned
    assert "\n" not in cleaned


def test_clean_text_normalises_unicode_and_strips_bullets():
    cleaned = clean_text("• Fee is ₹85,000 per year")
    assert "•" not in cleaned
    assert "85,000" in cleaned


def test_clean_text_handles_empty_input():
    assert clean_text("") == ""
    assert clean_text(None or "") == ""


def test_normalize_for_matching_can_drop_stopwords():
    tokens = normalize_for_matching(
        "What is the minimum attendance required for the exam?", remove_stopwords=True
    ).split()
    assert "attendance" in tokens
    assert not (set(tokens) & get_stopwords())


# --- segmentation ----------------------------------------------------------


def test_sentence_tokenize_splits_on_sentence_boundaries():
    sentences = sentence_tokenize(
        "Attendance must be 75%. Students below 65% are detained. Is that clear?"
    )
    assert len(sentences) == 3


def test_sentence_tokenize_returns_empty_for_blank_input():
    assert sentence_tokenize("   ") == []


def test_word_tokenize_returns_tokens():
    tokens = word_tokenize("Attendance is 75%.")
    assert "Attendance" in tokens
    assert any("75" in t for t in tokens)


# --- chunking --------------------------------------------------------------


def _page(text: str, number: int = 1) -> PageText:
    return PageText(page_number=number, text=text)


def test_chunking_splits_long_text_into_multiple_chunks():
    body = " ".join(f"This is sentence number {i} of the college policy." for i in range(80))
    chunks = chunk_pages([_page(body)], chunk_size=500, chunk_overlap=100)
    assert len(chunks) > 1


def test_every_chunk_respects_the_size_budget():
    body = " ".join(f"Policy sentence {i} about college rules." for i in range(120))
    for chunk in chunk_pages([_page(body)], chunk_size=400, chunk_overlap=80):
        assert chunk.char_count <= 400


def test_consecutive_chunks_share_overlapping_text():
    sentences = [f"Unique marker {i} appears in this college policy sentence." for i in range(40)]
    chunks = chunk_pages([_page(" ".join(sentences))], chunk_size=400, chunk_overlap=120)
    assert len(chunks) >= 2
    first_words = set(chunks[0].text.split())
    second_words = set(chunks[1].text.split())
    assert first_words & second_words, "expected overlap between consecutive chunks"


def test_chunks_record_their_source_page_numbers():
    pages = [_page("Page one sentence about fees.", 1), _page("Page two sentence about exams.", 2)]
    chunks = chunk_pages(pages, chunk_size=500, chunk_overlap=50)
    all_pages = {p for c in chunks for p in c.pages}
    assert all_pages == {1, 2}


def test_a_single_oversized_sentence_is_hard_split():
    giant = "word " * 400  # one "sentence" far longer than the budget
    chunks = chunk_pages([_page(giant)], chunk_size=200, chunk_overlap=40)
    assert len(chunks) > 1
    assert all(c.char_count <= 200 for c in chunks)


def test_chunking_empty_pages_returns_no_chunks():
    assert chunk_pages([_page("")], chunk_size=500, chunk_overlap=100) == []


def test_overlap_larger_than_chunk_size_still_terminates():
    """A misconfiguration must not hang the ingestion worker."""
    body = " ".join(f"Sentence {i} here." for i in range(60))
    chunks = chunk_pages([_page(body)], chunk_size=200, chunk_overlap=500)
    assert len(chunks) > 1


def test_page_label_formats_single_and_multi_page_chunks():
    assert Chunk(chunk_id="c", text="t", pages=[3]).page_label == "3"
    assert Chunk(chunk_id="c", text="t", pages=[3, 4, 5]).page_label == "3-5"


# --- extraction ------------------------------------------------------------


def test_extract_real_pdf_returns_pages_with_text(tmp_path):
    samples = Path(__file__).resolve().parents[2] / "documents" / "samples"
    pdf = samples / "attendance_policy.pdf"
    if not pdf.exists():
        pytest.skip("Sample PDFs not generated")

    pages = extract_document(pdf)
    assert len(pages) >= 1
    assert has_extractable_text(pages)
    assert "attendance" in " ".join(p.text for p in pages).lower()


def test_extract_rejects_unsupported_extension(tmp_path):
    bad = tmp_path / "notes.docx"
    bad.write_bytes(b"whatever")
    with pytest.raises(ExtractionError, match="Unsupported file type"):
        extract_document(bad)


def test_extract_rejects_a_corrupt_pdf(tmp_path):
    fake = tmp_path / "broken.pdf"
    fake.write_bytes(b"%PDF-1.4\nthis is not actually a pdf body")
    with pytest.raises(ExtractionError):
        extract_document(fake)


def test_has_extractable_text_detects_an_image_only_document():
    assert not has_extractable_text([PageText(page_number=1, text="   ")])


# --- prompt ----------------------------------------------------------------


def _chunk(text: str, title: str = "Attendance Policy", similarity: float = 0.8) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id="c1",
        text=text,
        similarity=similarity,
        document_id=1,
        filename="attendance_policy.pdf",
        title=title,
        page_number=1,
        page_label="1",
        department="Academics",
        document_type="policy",
        academic_year="2025-26",
    )


def test_prompt_contains_the_context_and_the_question():
    prompt = build_prompt("What is the attendance rule?", [_chunk("Minimum 75% attendance.")], [])
    assert "Minimum 75% attendance." in prompt
    assert "What is the attendance rule?" in prompt


def test_prompt_instructs_the_model_to_refuse_when_context_is_thin():
    prompt = build_prompt("Anything?", [_chunk("Some text.")], [])
    assert FALLBACK_MESSAGE in prompt
    assert "ONLY" in prompt


def test_prompt_forbids_disclosing_internals():
    prompt = build_prompt("Anything?", [_chunk("Some text.")], [])
    assert "embeddings" in prompt.lower()
    assert "never reveal" in prompt.lower()


def test_format_context_reports_no_context_when_empty():
    assert "no relevant" in format_context([]).lower()


def test_prompt_includes_conversation_history():
    history = [{"role": "user", "content": "What are the hostel fees?"}]
    prompt = build_prompt("Does that include meals?", [_chunk("Mess is included.")], history)
    assert "What are the hostel fees?" in prompt


# --- citations and follow-up handling --------------------------------------


def test_citations_are_deduplicated_per_document():
    chunks = [
        _chunk("First passage.", similarity=0.7),
        _chunk("Second passage.", similarity=0.9),
    ]
    citations = _build_citations(chunks)
    assert len(citations) == 1
    assert citations[0].similarity == 0.9  # best-scoring chunk wins


def test_citations_keep_distinct_documents_separate():
    other = _chunk("Fee text.", title="Fee Structure")
    other.document_id = 2
    other.filename = "fees_structure.pdf"
    citations = _build_citations([_chunk("Attendance text."), other])
    assert {c.title for c in citations} == {"Attendance Policy", "Fee Structure"}


def test_long_snippets_are_truncated():
    citation = _build_citations([_chunk("word " * 300)])[0]
    assert citation.snippet.endswith("...")
    assert len(citation.snippet) <= 330


def test_followup_question_is_expanded_with_the_previous_turn():
    history = [
        {"role": "user", "content": "What are the hostel fees?"},
        {"role": "assistant", "content": "Rs. 72,000 for a two-seater."},
    ]
    assert "hostel fees" in _contextualize("Does that include meals?", history)


def test_first_question_is_not_expanded():
    assert _contextualize("What are the hostel fees?", []) == "What are the hostel fees?"


# --- follow-up detection (decides query rewriting only) ---------------------

from app.rag.pipeline import is_follow_up  # noqa: E402


@pytest.mark.parametrize(
    "question",
    [
        "Does that include meals?",
        "And the even semester ones?",
        "What about the lab?",
        "Even semester?",
        "How much does it cost?",
        "Is the same true for hostel students?",
    ],
)
def test_dependent_questions_are_detected_as_follow_ups(question):
    assert is_follow_up(question)


@pytest.mark.parametrize(
    "question",
    [
        "Who is the current chief minister of the state?",
        "What is the fee for hostel accommodation for a year?",
        "How do I apply for a merit scholarship?",
        "When are the semester end examinations held?",
    ],
)
def test_self_contained_questions_are_not_follow_ups(question):
    assert not is_follow_up(question)


def test_an_unrelated_question_is_not_merged_with_the_previous_topic():
    """Regression: folding an earlier hostel question into an off-topic one
    inflated its similarity past the threshold."""
    history = [
        {"role": "user", "content": "What is the fee for hostel accommodation for a year?"},
        {"role": "assistant", "content": "Rs. 72,000 for a two-seater room."},
    ]
    question = "Who is the current chief minister of the state?"
    assert _contextualize(question, history) == question


# --- output normalisation -------------------------------------------------

from app.rag.pipeline import normalize_markdown  # noqa: E402


def test_glyph_bullets_become_markdown_list_items():
    raw = "* Third Year Subjects\n  \u2022 Algorithms\n  \u2022 Databases"
    assert normalize_markdown(raw) == "* Third Year Subjects\n  - Algorithms\n  - Databases"


def test_normalize_markdown_leaves_ordinary_text_alone():
    text = "The fee is Rs. 72,000.\n\n- already a list item"
    assert normalize_markdown(text) == text


def test_inline_bullet_characters_mid_sentence_are_untouched():
    text = "Timings: 9 a.m. \u2022 5 p.m."
    assert normalize_markdown(text) == text
