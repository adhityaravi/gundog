"""Configuration loading for gundog."""

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from gundog._templates import IgnorePreset


@dataclass
class SourceConfig:
    """Configuration for a single source directory."""

    path: str
    glob: str = "**/*"
    type: str | None = None  # optional user-defined category for filtering
    ignore: list[str] = field(default_factory=list)
    ignore_preset: IgnorePreset | None = None  # predefined ignore patterns
    use_gitignore: bool = True  # auto-read .gitignore if exists


@dataclass
class EmbeddingConfig:
    """Configuration for the embedding model."""

    model: str = "BAAI/bge-small-en-v1.5"


@dataclass
class StorageConfig:
    """Configuration for vector storage."""

    backend: str = "numpy"  # "numpy" | "lancedb"
    path: str = ".gundog/index"


@dataclass
class GraphConfig:
    """Configuration for similarity graph."""

    similarity_threshold: float = 0.65  # Minimum similarity for edge
    expand_threshold: float = 0.60  # Minimum edge weight for expansion
    max_expand_depth: int = 1  # How many hops to expand


@dataclass
class HybridConfig:
    """Configuration for hybrid search (vector + BM25)."""

    enabled: bool = True  # Default ON for better results
    bm25_weight: float = 0.5
    vector_weight: float = 0.5


@dataclass
class ChunkingConfig:
    """Configuration for text chunking."""

    enabled: bool = False  # Opt-in for backward compatibility
    max_tokens: int = 512
    overlap_tokens: int = 50


@dataclass
class GundogConfig:
    """Root configuration object."""

    sources: list[SourceConfig]
    embedding: EmbeddingConfig = field(default_factory=EmbeddingConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    graph: GraphConfig = field(default_factory=GraphConfig)
    hybrid: HybridConfig = field(default_factory=HybridConfig)
    chunking: ChunkingConfig = field(default_factory=ChunkingConfig)

    @classmethod
    def load(cls, config_path: Path | None = None) -> "GundogConfig":
        """Load config from file, falling back to defaults."""
        if config_path is None:
            config_path = Path(".gundog/config.yaml")

        if not config_path.exists():
            raise FileNotFoundError(f"Config not found: {config_path}")

        with open(config_path) as f:
            data = yaml.safe_load(f)

        # Parse sources with ignore_preset support
        sources = []
        for s in data.get("sources", []):
            # Convert ignore_preset string to enum if present
            if "ignore_preset" in s and s["ignore_preset"] is not None:
                s["ignore_preset"] = IgnorePreset(s["ignore_preset"])
            sources.append(SourceConfig(**s))

        embedding_data = data.get("embedding", {})
        embedding = EmbeddingConfig(**embedding_data) if embedding_data else EmbeddingConfig()

        storage_data = data.get("storage", {})
        storage = StorageConfig(**storage_data) if storage_data else StorageConfig()

        graph_data = data.get("graph", {})
        graph = GraphConfig(**graph_data) if graph_data else GraphConfig()

        hybrid_data = data.get("hybrid", {})
        hybrid = HybridConfig(**hybrid_data) if hybrid_data else HybridConfig()

        chunking_data = data.get("chunking", {})
        chunking = ChunkingConfig(**chunking_data) if chunking_data else ChunkingConfig()

        return cls(
            sources=sources,
            embedding=embedding,
            storage=storage,
            graph=graph,
            hybrid=hybrid,
            chunking=chunking,
        )
