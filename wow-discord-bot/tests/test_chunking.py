"""Tests for the word-level chunker used before embedding guide text.

chunk_text is imported directly — importing the embedder module does NOT pull
in sentence-transformers (that's loaded lazily inside get_model), so these run
fast with no heavy ML deps installed.
"""
from services.knowledge_base.embedder import chunk_text


def test_empty_text_yields_no_chunks():
    assert chunk_text("") == []
    assert chunk_text("   ") == []


def test_short_text_is_single_chunk():
    text = "just a few words here"
    chunks = chunk_text(text, chunk_size=400, overlap=50)
    assert chunks == [text]


def test_chunks_overlap_by_configured_amount():
    words = [f"w{i}" for i in range(10)]
    text = " ".join(words)

    chunks = chunk_text(text, chunk_size=4, overlap=1)

    # step = chunk_size - overlap = 3 -> starts at 0, 3, 6, 9
    assert len(chunks) == 4
    assert chunks[0].split() == ["w0", "w1", "w2", "w3"]
    # last word of chunk 0 reappears as first word of chunk 1 (the overlap)
    assert chunks[0].split()[-1] == chunks[1].split()[0] == "w3"
    assert chunks[-1].split() == ["w9"]


def test_no_overlap_tiles_without_repeats():
    text = " ".join(str(i) for i in range(6))
    chunks = chunk_text(text, chunk_size=2, overlap=0)
    assert chunks == ["0 1", "2 3", "4 5"]
