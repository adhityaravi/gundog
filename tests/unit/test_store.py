"""Test vector store implementations."""

from pathlib import Path

import numpy as np

from gundog._store._numpy_store import NumpyStore


def test_numpy_store_init(temp_dir: Path):
    """Test NumpyStore initialization creates directory."""
    store_path = temp_dir / "index"
    store = NumpyStore(store_path)

    assert store_path.exists()
    assert store.all_ids() == []


def test_numpy_store_upsert_and_get(temp_dir: Path):
    """Test inserting and retrieving vectors."""
    store = NumpyStore(temp_dir / "index")

    # Create a normalized vector
    vec = np.random.rand(384).astype(np.float32)
    vec = vec / np.linalg.norm(vec)

    metadata = {"type": "adr", "mtime": 1234.5}

    store.upsert("file1.md", vec, metadata)

    result = store.get("file1.md")
    assert result is not None

    retrieved_vec, retrieved_meta = result
    np.testing.assert_array_almost_equal(retrieved_vec, vec)
    assert retrieved_meta["type"] == "adr"
    assert retrieved_meta["mtime"] == 1234.5


def test_numpy_store_upsert_update(temp_dir: Path):
    """Test updating an existing vector."""
    store = NumpyStore(temp_dir / "index")

    vec1 = np.random.rand(384).astype(np.float32)
    vec1 = vec1 / np.linalg.norm(vec1)
    vec2 = np.random.rand(384).astype(np.float32)
    vec2 = vec2 / np.linalg.norm(vec2)

    store.upsert("file1.md", vec1, {"version": 1})
    store.upsert("file1.md", vec2, {"version": 2})

    assert len(store.all_ids()) == 1

    result = store.get("file1.md")
    assert result is not None

    retrieved_vec, retrieved_meta = result
    np.testing.assert_array_almost_equal(retrieved_vec, vec2)
    assert retrieved_meta["version"] == 2


def test_numpy_store_delete(temp_dir: Path):
    """Test deleting vectors."""
    store = NumpyStore(temp_dir / "index")

    vec = np.random.rand(384).astype(np.float32)
    vec = vec / np.linalg.norm(vec)

    store.upsert("file1.md", vec, {"type": "adr"})
    store.upsert("file2.md", vec, {"type": "code"})

    assert len(store.all_ids()) == 2

    result = store.delete("file1.md")
    assert result is True

    assert len(store.all_ids()) == 1
    assert store.get("file1.md") is None
    assert store.get("file2.md") is not None


def test_numpy_store_delete_nonexistent(temp_dir: Path):
    """Test deleting nonexistent vector returns False."""
    store = NumpyStore(temp_dir / "index")
    result = store.delete("nonexistent.md")
    assert result is False


def test_numpy_store_search(temp_dir: Path):
    """Test vector similarity search."""
    store = NumpyStore(temp_dir / "index")

    # Create vectors with known relationships
    base_vec = np.random.rand(384).astype(np.float32)
    base_vec = base_vec / np.linalg.norm(base_vec)

    # Similar vector (small perturbation)
    similar_vec = base_vec + 0.1 * np.random.rand(384).astype(np.float32)
    similar_vec = similar_vec / np.linalg.norm(similar_vec)

    # Different vector
    different_vec = np.random.rand(384).astype(np.float32)
    different_vec = different_vec / np.linalg.norm(different_vec)

    store.upsert("base.md", base_vec, {"type": "base"})
    store.upsert("similar.md", similar_vec, {"type": "similar"})
    store.upsert("different.md", different_vec, {"type": "different"})

    # Search with base vector
    results = store.search(base_vec, top_k=2)

    assert len(results) == 2
    assert results[0].id == "base.md"  # Should match itself best
    assert results[0].score > 0.99  # Should be very close to 1.0


def test_numpy_store_search_empty(temp_dir: Path):
    """Test search on empty store returns empty list."""
    store = NumpyStore(temp_dir / "index")
    query_vec = np.random.rand(384).astype(np.float32)

    results = store.search(query_vec, top_k=10)
    assert results == []


def test_numpy_store_save_and_load(temp_dir: Path):
    """Test persistence to disk and loading."""
    store_path = temp_dir / "index"
    store = NumpyStore(store_path)

    vec1 = np.random.rand(384).astype(np.float32)
    vec1 = vec1 / np.linalg.norm(vec1)
    vec2 = np.random.rand(384).astype(np.float32)
    vec2 = vec2 / np.linalg.norm(vec2)

    store.upsert("file1.md", vec1, {"type": "adr"})
    store.upsert("file2.md", vec2, {"type": "code"})
    store.save()

    # Create new store and load
    store2 = NumpyStore(store_path)
    store2.load()

    assert len(store2.all_ids()) == 2

    result = store2.get("file1.md")
    assert result is not None
    retrieved_vec, retrieved_meta = result
    np.testing.assert_array_almost_equal(retrieved_vec, vec1)
    assert retrieved_meta["type"] == "adr"


def test_numpy_store_all_vectors(temp_dir: Path):
    """Test retrieving all vectors for graph building."""
    store = NumpyStore(temp_dir / "index")

    vectors = {}
    for i in range(3):
        vec = np.random.rand(384).astype(np.float32)
        vec = vec / np.linalg.norm(vec)
        vectors[f"file_{i}.md"] = vec
        store.upsert(f"file_{i}.md", vec, {"type": "adr"})

    all_vecs = store.all_vectors()

    assert len(all_vecs) == 3
    for key, vec in vectors.items():
        np.testing.assert_array_almost_equal(all_vecs[key], vec)


def test_numpy_store_get_batch(temp_dir: Path):
    """Test batch retrieval of vectors and metadata."""
    store = NumpyStore(temp_dir / "index")

    vectors = {}
    for i in range(5):
        vec = np.random.rand(384).astype(np.float32)
        vec = vec / np.linalg.norm(vec)
        vectors[f"file_{i}.md"] = vec
        store.upsert(f"file_{i}.md", vec, {"type": "adr", "index": i})

    # Batch get subset
    result = store.get_batch(["file_0.md", "file_2.md", "file_4.md"])

    assert len(result) == 3
    assert "file_0.md" in result
    assert "file_2.md" in result
    assert "file_4.md" in result
    assert "file_1.md" not in result

    # Verify vector and metadata
    vec, meta = result["file_2.md"]
    np.testing.assert_array_almost_equal(vec, vectors["file_2.md"])
    assert meta["index"] == 2


def test_numpy_store_get_batch_with_missing(temp_dir: Path):
    """Test batch retrieval skips missing IDs."""
    store = NumpyStore(temp_dir / "index")

    vec = np.random.rand(384).astype(np.float32)
    vec = vec / np.linalg.norm(vec)
    store.upsert("exists.md", vec, {"type": "adr"})

    result = store.get_batch(["exists.md", "missing.md", "also_missing.md"])

    assert len(result) == 1
    assert "exists.md" in result
    assert "missing.md" not in result


def test_numpy_store_get_batch_empty(temp_dir: Path):
    """Test batch retrieval with empty list."""
    store = NumpyStore(temp_dir / "index")

    vec = np.random.rand(384).astype(np.float32)
    store.upsert("file.md", vec, {"type": "adr"})

    result = store.get_batch([])
    assert result == {}
