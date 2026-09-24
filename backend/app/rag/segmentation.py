"""Sentence and word segmentation, with regex fallbacks for offline runs."""

import re

from app.rag.text_cleaner import ensure_nltk_data

_ABBREVIATIONS = r"(?:Mr|Mrs|Ms|Dr|Prof|Sr|Jr|vs|etc|e\.g|i\.e|No|Fig|approx|Sec|Cl)\."
_SENTENCE_SPLIT_RE = re.compile(r"(?<!\w\.\w.)(?<![A-Z][a-z]\.)(?<=\.|\?|!)\s+(?=[A-Z(\d])")


def sentence_tokenize(text: str) -> list[str]:
    """Split text into sentences using NLTK Punkt, falling back to regex."""
    if not text or not text.strip():
        return []

    ensure_nltk_data()
    try:
        import nltk

        sentences = nltk.sent_tokenize(text)
    except Exception:  # noqa: BLE001 - missing punkt data or no nltk
        sentences = _regex_sentence_split(text)

    return [s.strip() for s in sentences if s.strip()]


def _regex_sentence_split(text: str) -> list[str]:
    protected = re.sub(_ABBREVIATIONS, lambda m: m.group(0).replace(".", "<DOT>"), text)
    parts = _SENTENCE_SPLIT_RE.split(protected)
    return [p.replace("<DOT>", ".") for p in parts]


def word_tokenize(text: str) -> list[str]:
    ensure_nltk_data()
    try:
        import nltk

        return nltk.word_tokenize(text)
    except Exception:  # noqa: BLE001
        return re.findall(r"[A-Za-z0-9']+|[.,!?;:%]", text)
