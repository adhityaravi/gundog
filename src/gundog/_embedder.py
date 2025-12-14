"""Text embedding using sentence-transformers."""

from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer


class Embedder:
    """Handles text embedding using sentence-transformers."""

    def __init__(self, model_name: str = "BAAI/bge-small-en-v1.5"):
        """
        Initialize embedder with specified model.

        Args:
            model_name: HuggingFace model identifier. Options:
                - "BAAI/bge-small-en-v1.5" (default, 130MB, good quality)
                - "sentence-transformers/all-MiniLM-L6-v2" (80MB, faster)
                - "BAAI/bge-base-en-v1.5" (440MB, better quality)
        """
        self.model_name = model_name
        self._model: SentenceTransformer | None = None

    @property
    def model(self) -> "SentenceTransformer":
        """Lazy load model on first use."""
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self.model_name)
        return self._model

    @property
    def dimensions(self) -> int:
        """Return embedding dimensions for this model."""
        dim = self.model.get_sentence_embedding_dimension()
        if dim is None:
            raise ValueError(f"Could not get embedding dimensions for model {self.model_name}")
        return dim

    def embed_text(self, text: str) -> np.ndarray:
        """
        Embed a single text string.

        Args:
            text: Text to embed

        Returns:
            Normalized embedding vector
        """
        embedding = self.model.encode(text, normalize_embeddings=True)
        return np.asarray(embedding)

    def embed_file(self, file_path: Path) -> np.ndarray:
        """
        Embed a file's contents with path context.

        The file path is prepended to help the model understand
        the file's role (e.g., "adr/networking/..." signals networking content).

        Args:
            file_path: Path to file to embed

        Returns:
            Normalized embedding vector
        """
        content = file_path.read_text(encoding="utf-8")
        # Include path for context - helps with clustering
        full_content = f"Path: {file_path}\n\n{content}"
        return self.embed_text(full_content)

    def embed_batch(self, texts: list[str], show_progress: bool = True) -> np.ndarray:
        """
        Embed multiple texts efficiently in batch.

        Args:
            texts: List of texts to embed
            show_progress: Show progress bar

        Returns:
            Array of normalized embeddings, shape (len(texts), dimensions)
        """
        embeddings = self.model.encode(
            texts,
            normalize_embeddings=True,
            show_progress_bar=show_progress,
        )
        return np.asarray(embeddings)
