"""Text embedding using ONNX Runtime for faster inference."""

from pathlib import Path
from typing import Any

import numpy as np

# Import triggers thread limit defaults
from gundog._embedder import DEFAULT_THREADS


class ONNXEmbedder:
    """
    Handles text embedding using ONNX Runtime.

    Provides ~2.7x faster inference compared to PyTorch sentence-transformers,
    with better noise rejection for irrelevant queries.

    Models are automatically converted to ONNX on first use and cached at:
        ~/.cache/gundog/onnx/{model_name}/
    This cache is shared across all projects using the same model.
    """

    def __init__(
        self,
        model_name: str = "BAAI/bge-small-en-v1.5",
        cache_dir: Path | None = None,
        threads: int = DEFAULT_THREADS,
    ):
        """
        Initialize ONNX embedder.

        Args:
            model_name: HuggingFace model identifier
            cache_dir: Directory containing ONNX model files.
                       Default: ~/.cache/gundog/onnx/{model_safe_name}/
            threads: Number of CPU threads for ONNX inference
        """
        self.model_name = model_name
        self._safe_name = model_name.replace("/", "--")
        self._threads = threads

        if cache_dir is None:
            self._cache_dir = Path.home() / ".cache" / "gundog" / "onnx" / self._safe_name
        else:
            self._cache_dir = Path(cache_dir)

        self._session: Any = None  # onnxruntime.InferenceSession
        self._tokenizer: Any = None  # transformers.AutoTokenizer
        self._dimensions: int | None = None

    def _ensure_model(self) -> None:
        """Load ONNX model and tokenizer on first use."""
        if self._session is not None:
            return

        try:
            import onnxruntime as ort
        except ImportError as e:
            raise ImportError(
                "onnxruntime is not installed. Install with: pip install gundog[onnx]"
            ) from e

        model_path = self._cache_dir / "model.onnx"
        if not model_path.exists():
            # Auto-convert model to ONNX on first use
            print(f"ONNX model not found. Converting {self.model_name} to ONNX...")
            convert_to_onnx(self.model_name, self._cache_dir)

        # Load ONNX session with optimizations
        sess_options = ort.SessionOptions()
        sess_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        sess_options.intra_op_num_threads = self._threads

        self._session = ort.InferenceSession(
            str(model_path),
            sess_options=sess_options,
            providers=["CPUExecutionProvider"],
        )

        # Load tokenizer
        try:
            from transformers import AutoTokenizer
        except ImportError as e:
            raise ImportError(
                "transformers is not installed. Install with: pip install transformers"
            ) from e

        self._tokenizer = AutoTokenizer.from_pretrained(str(self._cache_dir))

        # Detect dimensions from model output
        output_shape = self._session.get_outputs()[0].shape
        if output_shape and len(output_shape) > 1:
            self._dimensions = output_shape[-1]

    @property
    def dimensions(self) -> int:
        """Return embedding dimensions for this model."""
        self._ensure_model()
        if self._dimensions is None:
            # Run a test embedding to detect dimensions
            test_emb = self.embed_text("test")
            self._dimensions = test_emb.shape[0]
        assert self._dimensions is not None
        return self._dimensions

    def _mean_pooling(
        self, token_embeddings: np.ndarray, attention_mask: np.ndarray
    ) -> np.ndarray:
        """Apply mean pooling over token embeddings."""
        # Expand attention mask to match embedding dimensions
        input_mask_expanded = np.expand_dims(attention_mask, axis=-1)
        input_mask_expanded = np.broadcast_to(input_mask_expanded, token_embeddings.shape).astype(
            np.float32
        )

        # Sum embeddings weighted by attention mask
        sum_embeddings = np.sum(token_embeddings * input_mask_expanded, axis=1)
        sum_mask = np.clip(np.sum(input_mask_expanded, axis=1), a_min=1e-9, a_max=None)

        return sum_embeddings / sum_mask

    def _normalize(self, embeddings: np.ndarray) -> np.ndarray:
        """L2 normalize embeddings."""
        norms = np.linalg.norm(embeddings, axis=-1, keepdims=True)
        norms = np.clip(norms, a_min=1e-9, a_max=None)
        return embeddings / norms

    def embed_text(self, text: str) -> np.ndarray:
        """
        Embed a single text string.

        Args:
            text: Text to embed

        Returns:
            Normalized embedding vector
        """
        self._ensure_model()

        # Tokenize
        inputs = self._tokenizer(
            text,
            padding=True,
            truncation=True,
            max_length=512,
            return_tensors="np",
        )

        # Run ONNX inference
        ort_inputs = {
            "input_ids": inputs["input_ids"].astype(np.int64),
            "attention_mask": inputs["attention_mask"].astype(np.int64),
        }

        # Add token_type_ids if model expects it
        input_names = [inp.name for inp in self._session.get_inputs()]
        if "token_type_ids" in input_names:
            if "token_type_ids" in inputs:
                ort_inputs["token_type_ids"] = inputs["token_type_ids"].astype(np.int64)
            else:
                ort_inputs["token_type_ids"] = np.zeros_like(inputs["input_ids"], dtype=np.int64)

        outputs = self._session.run(None, ort_inputs)

        # Get token embeddings (usually first output)
        token_embeddings = outputs[0]

        # Mean pooling
        embeddings = self._mean_pooling(token_embeddings, inputs["attention_mask"])

        # Normalize
        embeddings = self._normalize(embeddings)

        return embeddings[0].astype(np.float32)

    def embed_batch(self, texts: list[str], show_progress: bool = True) -> np.ndarray:
        """
        Embed multiple texts.

        Args:
            texts: List of texts to embed
            show_progress: Show progress bar (for compatibility, uses tqdm if available)

        Returns:
            Array of normalized embeddings, shape (len(texts), dimensions)
        """
        self._ensure_model()

        if not texts:
            return np.array([], dtype=np.float32)

        # For progress display
        iterator = texts
        if show_progress:
            try:
                from tqdm import tqdm

                iterator = tqdm(texts, desc="Embedding")
            except ImportError:
                pass

        # Process in batches for memory efficiency
        batch_size = 32
        all_embeddings = []

        for i in range(0, len(texts), batch_size):
            batch_texts = texts[i : i + batch_size]

            # Tokenize batch
            inputs = self._tokenizer(
                batch_texts,
                padding=True,
                truncation=True,
                max_length=512,
                return_tensors="np",
            )

            # Run ONNX inference
            ort_inputs = {
                "input_ids": inputs["input_ids"].astype(np.int64),
                "attention_mask": inputs["attention_mask"].astype(np.int64),
            }

            input_names = [inp.name for inp in self._session.get_inputs()]
            if "token_type_ids" in input_names:
                if "token_type_ids" in inputs:
                    ort_inputs["token_type_ids"] = inputs["token_type_ids"].astype(np.int64)
                else:
                    ort_inputs["token_type_ids"] = np.zeros_like(
                        inputs["input_ids"], dtype=np.int64
                    )

            outputs = self._session.run(None, ort_inputs)
            token_embeddings = outputs[0]

            # Mean pooling and normalize
            embeddings = self._mean_pooling(token_embeddings, inputs["attention_mask"])
            embeddings = self._normalize(embeddings)

            all_embeddings.append(embeddings)

            # Update progress (tqdm has update/close methods)
            if show_progress:
                update_fn = getattr(iterator, "update", None)
                if update_fn:
                    update_fn(len(batch_texts))

        if show_progress:
            close_fn = getattr(iterator, "close", None)
            if close_fn:
                close_fn()

        return np.vstack(all_embeddings).astype(np.float32)

    @classmethod
    def is_available(cls, model_name: str) -> bool:
        """Check if ONNX model is available for the given model name."""
        safe_name = model_name.replace("/", "--")
        cache_dir = Path.home() / ".cache" / "gundog" / "onnx" / safe_name
        return (cache_dir / "model.onnx").exists()


def convert_to_onnx(
    model_name: str,
    output_dir: Path | None = None,
) -> Path:
    """
    Convert a sentence-transformers model to ONNX format.

    Args:
        model_name: HuggingFace model identifier (e.g., "BAAI/bge-small-en-v1.5")
        output_dir: Directory to save ONNX model. Default: ~/.cache/gundog/onnx/{model_name}/

    Returns:
        Path to the output directory containing ONNX model
    """
    try:
        from optimum.onnxruntime import ORTModelForFeatureExtraction
        from transformers import AutoTokenizer
    except ImportError as e:
        raise ImportError(
            "optimum and transformers are required for ONNX conversion. "
            "Install with: pip install gundog[onnx]"
        ) from e

    safe_name = model_name.replace("/", "--")
    if output_dir is None:
        output_dir = Path.home() / ".cache" / "gundog" / "onnx" / safe_name

    output_dir.mkdir(parents=True, exist_ok=True)

    # Export model to ONNX
    # Note: We always use export=True for consistent embeddings across all models.
    # HuggingFace's pre-converted ONNX may differ slightly due to version differences.
    print(f"Converting {model_name} to ONNX format...")
    import logging

    # Suppress optimum's "already converted" warning (it's printed, not warned)
    optimum_logger = logging.getLogger("optimum")
    original_level = optimum_logger.level
    optimum_logger.setLevel(logging.ERROR)
    try:
        model = ORTModelForFeatureExtraction.from_pretrained(
            model_name,
            export=True,
        )
    finally:
        optimum_logger.setLevel(original_level)

    # Save ONNX model
    model.save_pretrained(output_dir)

    # Save tokenizer
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    tokenizer.save_pretrained(output_dir)

    print(f"ONNX model saved to: {output_dir}")
    return output_dir
