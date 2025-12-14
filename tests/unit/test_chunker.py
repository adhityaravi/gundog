"""Test text chunking."""

from gundog._chunker import Chunk, chunk_text, make_chunk_id, parse_chunk_id


def test_chunk_dataclass():
    """Test Chunk dataclass."""
    chunk = Chunk(text="Hello world", index=0, start_char=0, end_char=11)
    assert chunk.text == "Hello world"
    assert chunk.index == 0
    assert chunk.start_char == 0
    assert chunk.end_char == 11


def test_chunk_text_empty():
    """Test chunking empty text."""
    chunks = chunk_text("")
    assert chunks == []

    chunks = chunk_text("   ")
    assert chunks == []


def test_chunk_text_small():
    """Test chunking text smaller than max_tokens."""
    text = "This is a small piece of text."
    chunks = chunk_text(text, max_tokens=512)

    assert len(chunks) == 1
    assert chunks[0].text == text
    assert chunks[0].index == 0


def test_chunk_text_large():
    """Test chunking large text creates multiple chunks."""
    # Create text larger than one chunk (512 tokens ~ 2048 chars)
    text = "This is a sentence. " * 200  # ~4000 chars

    chunks = chunk_text(text, max_tokens=512, overlap_tokens=50)

    assert len(chunks) > 1
    # Check indices are sequential
    for i, chunk in enumerate(chunks):
        assert chunk.index == i


def test_chunk_text_overlap():
    """Test that chunks overlap."""
    text = "Word " * 1000  # ~5000 chars

    chunks = chunk_text(text, max_tokens=256, overlap_tokens=50)

    assert len(chunks) > 2

    # Check overlap exists (end of chunk n should overlap with start of chunk n+1)
    for i in range(len(chunks) - 1):
        # The end of one chunk and start of next should have overlapping positions
        assert chunks[i].end_char > chunks[i + 1].start_char


def test_chunk_text_prefers_paragraph_breaks():
    """Test that chunking prefers paragraph breaks."""
    # Create text with clear paragraph breaks
    paragraph = "This is a paragraph with some content.\n\n"
    text = paragraph * 20  # Enough to need chunking

    chunks = chunk_text(text, max_tokens=256)

    # Check that chunks tend to end at paragraph boundaries
    for chunk in chunks[:-1]:  # Exclude last chunk
        # Should end near a paragraph break
        assert "\n" in chunk.text[-50:] or chunk.end_char == len(text)


def test_make_chunk_id():
    """Test creating chunk IDs."""
    chunk_id = make_chunk_id("path/to/file.py", 0)
    assert chunk_id == "path/to/file.py#chunk_0"

    chunk_id = make_chunk_id("file.md", 5)
    assert chunk_id == "file.md#chunk_5"


def test_parse_chunk_id():
    """Test parsing chunk IDs."""
    file_id, chunk_idx = parse_chunk_id("path/to/file.py#chunk_0")
    assert file_id == "path/to/file.py"
    assert chunk_idx == 0

    file_id, chunk_idx = parse_chunk_id("file.md#chunk_5")
    assert file_id == "file.md"
    assert chunk_idx == 5


def test_parse_chunk_id_not_chunk():
    """Test parsing non-chunk IDs."""
    file_id, chunk_idx = parse_chunk_id("path/to/file.py")
    assert file_id == "path/to/file.py"
    assert chunk_idx is None


def test_parse_chunk_id_invalid():
    """Test parsing invalid chunk IDs."""
    file_id, chunk_idx = parse_chunk_id("file.md#chunk_invalid")
    assert file_id == "file.md#chunk_invalid"
    assert chunk_idx is None


def test_chunk_roundtrip():
    """Test that make_chunk_id and parse_chunk_id are inverses."""
    original_file = "src/module/file.py"
    original_idx = 3

    chunk_id = make_chunk_id(original_file, original_idx)
    parsed_file, parsed_idx = parse_chunk_id(chunk_id)

    assert parsed_file == original_file
    assert parsed_idx == original_idx
