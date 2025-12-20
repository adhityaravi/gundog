"""Text chunking for improved embedding quality."""

import re
from dataclasses import dataclass


@dataclass
class Chunk:
    """A chunk of text from a file."""

    text: str
    index: int
    start_char: int
    end_char: int


def _estimate_tokens(text: str) -> int:
    """
    Estimate token count.

    Simple heuristic: ~4 characters per token (common for English text).
    """
    return len(text) // 4


def _find_split_point(text: str, target_pos: int, window: int = 200) -> int:
    """
    Find a good split point near target_pos.

    Prefers splitting at:
    1. Double newlines (paragraph breaks)
    2. Single newlines
    3. Sentence endings (. ! ?)
    4. Clause boundaries (, ; :)
    5. Word boundaries (spaces)
    """
    start = max(0, target_pos - window)
    end = min(len(text), target_pos + window)
    search_region = text[start:end]

    # Priority order of split patterns
    patterns = [
        r"\n\n",  # Paragraph break
        r"\n",  # Line break
        r"[.!?]\s",  # Sentence end
        r"[,;:]\s",  # Clause boundary
        r"\s",  # Word boundary
    ]

    for pattern in patterns:
        matches = list(re.finditer(pattern, search_region))
        if matches:
            # Find match closest to target
            target_offset = target_pos - start
            closest = min(matches, key=lambda m: abs(m.end() - target_offset))
            return start + closest.end()

    # Fallback: split at target position
    return target_pos


def chunk_text(
    text: str,
    max_tokens: int = 512,
    overlap_tokens: int = 50,
) -> list[Chunk]:
    """
    Split text into overlapping chunks.

    Args:
        text: Input text to chunk
        max_tokens: Maximum tokens per chunk (estimated)
        overlap_tokens: Tokens to overlap between chunks

    Returns:
        List of Chunk objects
    """
    if not text.strip():
        return []

    # Convert token counts to character estimates
    max_chars = max_tokens * 4
    overlap_chars = overlap_tokens * 4

    # If text is small enough, return as single chunk
    if _estimate_tokens(text) <= max_tokens:
        return [Chunk(text=text, index=0, start_char=0, end_char=len(text))]

    chunks: list[Chunk] = []
    start = 0
    index = 0

    while start < len(text):
        # Calculate end position
        end = min(start + max_chars, len(text))

        # If not at the end, find a good split point
        if end < len(text):
            end = _find_split_point(text, end)

        chunk_text = text[start:end].strip()
        if chunk_text:
            chunks.append(
                Chunk(
                    text=chunk_text,
                    index=index,
                    start_char=start,
                    end_char=end,
                )
            )
            index += 1

        # Move start position, accounting for overlap
        start = end - overlap_chars
        if start <= chunks[-1].start_char if chunks else 0:
            # Avoid infinite loop: ensure we make progress
            start = end

    return chunks


def make_chunk_id(file_id: str, chunk_index: int) -> str:
    """Create a unique ID for a chunk."""
    return f"{file_id}#chunk_{chunk_index}"


def parse_chunk_id(chunk_id: str) -> tuple[str, int | None]:
    """
    Parse a chunk ID to extract file ID and chunk index.

    Returns:
        Tuple of (file_id, chunk_index) where chunk_index is None if not a chunk ID
    """
    if "#chunk_" in chunk_id:
        parts = chunk_id.rsplit("#chunk_", 1)
        try:
            return parts[0], int(parts[1])
        except ValueError:
            return chunk_id, None
    return chunk_id, None
