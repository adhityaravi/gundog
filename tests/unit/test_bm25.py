"""Test BM25 keyword search index."""

from pathlib import Path

from gundog._bm25 import BM25Index


def test_bm25_build_empty():
    """Test building index with empty documents."""
    index = BM25Index()
    index.build({})
    assert index.is_empty


def test_bm25_build_and_search():
    """Test building index and searching."""
    index = BM25Index()
    documents = {
        "doc1.md": "Python programming language tutorial",
        "doc2.md": "JavaScript web development framework",
        "doc3.md": "Python data science machine learning",
    }
    index.build(documents)

    assert not index.is_empty

    # Search for Python - should match doc1 and doc3
    results = index.search("python", top_k=10)
    assert len(results) == 2
    doc_ids = [r[0] for r in results]
    assert "doc1.md" in doc_ids
    assert "doc3.md" in doc_ids


def test_bm25_search_no_match():
    """Test search with no matching terms."""
    index = BM25Index()
    documents = {
        "doc1.md": "Python programming",
        "doc2.md": "JavaScript framework",
    }
    index.build(documents)

    results = index.search("rust cargo", top_k=10)
    assert len(results) == 0


def test_bm25_search_empty_query():
    """Test search with empty query."""
    index = BM25Index()
    documents = {"doc1.md": "Python programming"}
    index.build(documents)

    results = index.search("", top_k=10)
    assert len(results) == 0


def test_bm25_search_on_empty_index():
    """Test searching on empty index."""
    index = BM25Index()
    results = index.search("python", top_k=10)
    assert len(results) == 0


def test_bm25_tokenize():
    """Test tokenization."""
    index = BM25Index()
    tokens = index._tokenize("Hello, World! Python_code 123")
    assert "hello" in tokens
    assert "world" in tokens
    assert "python_code" in tokens
    assert "123" in tokens
    # Single character tokens should be filtered
    assert "a" not in index._tokenize("a b c")


def test_bm25_save_and_load(temp_dir: Path):
    """Test saving and loading index."""
    path = temp_dir / "bm25.pkl"
    index = BM25Index(path)
    documents = {
        "doc1.md": "Python programming language",
        "doc2.md": "JavaScript web framework",
        "doc3.md": "Rust systems programming",
    }
    index.build(documents)
    index.save()

    # Load into new index
    index2 = BM25Index(path)
    loaded = index2.load()

    assert loaded is True
    assert not index2.is_empty

    # Search should work - "python" appears in doc1 only
    results = index2.search("python", top_k=10)
    assert len(results) >= 1
    doc_ids = [r[0] for r in results]
    assert "doc1.md" in doc_ids


def test_bm25_load_nonexistent(temp_dir: Path):
    """Test loading from nonexistent file."""
    index = BM25Index(temp_dir / "nonexistent.pkl")
    loaded = index.load()
    assert loaded is False


def test_bm25_top_k_limit():
    """Test that top_k limits results."""
    index = BM25Index()
    # Each document has "programming" plus a unique term
    documents = {f"doc{i}.md": f"programming language{i} tutorial" for i in range(10)}
    index.build(documents)

    # Search for "programming" which appears in all docs
    # BM25 should still rank them (TF matters even with low IDF)
    results = index.search("programming tutorial", top_k=3)
    assert len(results) <= 3  # May return fewer if scores are 0
