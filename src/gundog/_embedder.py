"""Text embedding using sentence-transformers or ONNX Runtime."""

import os
from typing import TYPE_CHECKING, Protocol

import numpy as np

# Default thread limit (conservative to prevent system overload)
DEFAULT_THREADS = 2

# Thread limit env vars
_THREAD_ENV_VARS = [
    "OMP_NUM_THREADS",
    "MKL_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "VECLIB_MAXIMUM_THREADS",
    "NUMEXPR_NUM_THREADS",
]


def set_thread_limit(threads: int | None = None) -> None:
    """Set CPU thread limit for embedding operations.

    Must be called before importing torch/transformers for full effect.
    """
    t = str(threads if threads is not None else DEFAULT_THREADS)
    for var in _THREAD_ENV_VARS:
        os.environ[var] = t


# Set conservative defaults at import time (using setdefault to not override user env)
for _var in _THREAD_ENV_VARS:
    os.environ.setdefault(_var, str(DEFAULT_THREADS))

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer


class EmbedderProtocol(Protocol):
    """Protocol for embedder backends."""

    model_name: str

    @property
    def dimensions(self) -> int:
        """Return embedding dimensions for this model."""
        ...

    def embed_text(self, text: str) -> np.ndarray:
        """Embed a single text string."""
        ...

    def embed_batch(self, texts: list[str], show_progress: bool = True) -> np.ndarray:
        """Embed multiple texts efficiently in batch."""
        ...


def create_embedder(
    model_name: str = "BAAI/bge-small-en-v1.5",
    enable_onnx: bool = True,
    threads: int = DEFAULT_THREADS,
) -> "EmbedderProtocol":
    """
    Factory function to create the appropriate embedder.

    Args:
        model_name: HuggingFace model identifier
        enable_onnx: Use ONNX Runtime (default: True, 2.7x faster)
        threads: CPU threads for embedding (default: 2)

    Returns:
        Embedder instance

    ONNX models are cached in ~/.cache/gundog/onnx/ and shared across projects.
    """
    # Set thread limits early (before torch import)
    set_thread_limit(threads)

    if enable_onnx:
        # Lazy import to avoid circular dependency (_embedder_onnx imports DEFAULT_THREADS)
        from gundog._embedder_onnx import ONNXEmbedder

        return ONNXEmbedder(model_name, threads=threads)
    return Embedder(model_name)


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
