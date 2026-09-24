"""Text cleaning and normalization for PDF-extracted text and user questions."""

import re
import unicodedata

_NLTK_READY = False

# Used only for lightweight lexical signals (titles, keyword hints), never as
# the primary retrieval mechanism -- retrieval is embedding-based.
_FALLBACK_STOPWORDS = {
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "and", "or", "but", "if", "then", "so", "of", "to", "in", "on", "at",
    "for", "with", "as", "by", "this", "that", "these", "those", "it",
    "its", "from", "into", "than", "such", "not", "no", "do", "does",
    "did", "can", "could", "will", "would", "should", "may", "might",
    "what", "when", "where", "which", "who", "whom", "how", "why", "i",
    "my", "me", "we", "our", "you", "your", "there", "here",
}


def ensure_nltk_data() -> None:
    """Fetch NLTK corpora once; stay silent (and use fallbacks) when offline."""
    global _NLTK_READY
    if _NLTK_READY:
        return
    try:
        import nltk

        for pkg, path in [
            ("punkt", "tokenizers/punkt"),
            ("punkt_tab", "tokenizers/punkt_tab"),
            ("stopwords", "corpora/stopwords"),
        ]:
            try:
                nltk.data.find(path)
            except LookupError:
                try:
                    nltk.download(pkg, quiet=True)
                except Exception:  # noqa: BLE001 - offline is an acceptable state
                    pass
    except ImportError:
        pass
    _NLTK_READY = True


def get_stopwords() -> set[str]:
    ensure_nltk_data()
    try:
        from nltk.corpus import stopwords

        return set(stopwords.words("english"))
    except Exception:  # noqa: BLE001 - offline / corpus missing
        return set(_FALLBACK_STOPWORDS)


def clean_text(raw_text: str) -> str:
    """Normalize text extracted from a PDF page.

    Repairs hyphenated line-break splits, collapses whitespace, normalizes
    unicode (curly quotes, ligatures, non-breaking spaces) and strips bullet
    glyph noise, so that chunk boundaries and embeddings are not polluted by
    PDF layout artifacts.
    """
    if not raw_text:
        return ""

    text = unicodedata.normalize("NFKC", raw_text)
    text = text.replace(" ", " ")
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)
    text = re.sub(r"[\t\r]+", " ", text)
    text = re.sub(r"\n{2,}", "\n", text)
    text = re.sub(r"\n", " ", text)
    text = re.sub(r"[•●▪·]", " ", text)
    text = "".join(ch for ch in text if ch == "\n" or unicodedata.category(ch)[0] != "C")
    text = re.sub(r" {2,}", " ", text)
    return text.strip()


def normalize_for_matching(text: str, remove_stopwords: bool = False) -> str:
    """Lowercase, punctuation-stripped form used for titles and keyword hints."""
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s{2,}", " ", text).strip()
    if remove_stopwords:
        stop = get_stopwords()
        text = " ".join(t for t in text.split() if t not in stop)
    return text
