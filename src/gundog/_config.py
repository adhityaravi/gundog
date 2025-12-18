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
    enable_onnx: bool = True  # ONNX is faster and has better noise rejection
    threads: int = 2  # CPU threads for embedding (prevents system overload)


@dataclass
class StorageConfig:
    """Configuration for vector storage."""

    use_hnsw: bool = True  # HNSW scales better than numpy for large indexes
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
class RecencyConfig:
    """Configuration for recency-based score boosting."""

    enabled: bool = False  # Opt-in, requires git history
    weight: float = 0.15  # How much recency affects final score (0-1)
    half_life_days: int = 30  # Days until recency boost decays to 50%


@dataclass
class GundogConfig:
    """Root configuration object."""

    sources: list[SourceConfig]
    embedding: EmbeddingConfig = field(default_factory=EmbeddingConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    graph: GraphConfig = field(default_factory=GraphConfig)
    hybrid: HybridConfig = field(default_factory=HybridConfig)
    chunking: ChunkingConfig = field(default_factory=ChunkingConfig)
    recency: RecencyConfig = field(default_factory=RecencyConfig)

    @classmethod
    def bootstrap(cls, config_path: Path | None = None) -> Path:
        """
        Auto-detect sources and create a starter config file.

        Scans the current directory for common file types and creates
        appropriate source configurations.
        """
        if config_path is None:
            config_path = Path(".gundog/config.yaml")

        config_path.parent.mkdir(parents=True, exist_ok=True)

        # File type detection patterns
        type_patterns: dict[str, dict[str, str | None]] = {
            "py": {"glob": "**/*.py", "type": "code", "preset": "python"},
            "md": {"glob": "**/*.md", "type": "docs", "preset": None},
            "ts": {"glob": "**/*.ts", "type": "code", "preset": "typescript"},
            "tsx": {"glob": "**/*.tsx", "type": "code", "preset": "typescript"},
            "js": {"glob": "**/*.js", "type": "code", "preset": "javascript"},
            "jsx": {"glob": "**/*.jsx", "type": "code", "preset": "javascript"},
            "go": {"glob": "**/*.go", "type": "code", "preset": "go"},
            "rs": {"glob": "**/*.rs", "type": "code", "preset": "rust"},
            "java": {"glob": "**/*.java", "type": "code", "preset": "java"},
        }

        # Scan current directory for file types
        cwd = Path.cwd()
        found_types: set[str] = set()

        for ext in type_patterns:
            if list(cwd.glob(f"**/*.{ext}"))[:1]:  # Check if any files exist
                found_types.add(ext)

        # Build sources config
        sources: list[dict[str, str | None]] = []

        # Group by preset to avoid duplicate sources
        if found_types:
            # Combine ts/tsx and js/jsx
            if "ts" in found_types or "tsx" in found_types:
                sources.append(
                    {
                        "path": ".",
                        "glob": "**/*.{ts,tsx}",
                        "type": "code",
                        "ignore_preset": "typescript",
                    }
                )
                found_types.discard("ts")
                found_types.discard("tsx")

            if "js" in found_types or "jsx" in found_types:
                sources.append(
                    {
                        "path": ".",
                        "glob": "**/*.{js,jsx}",
                        "type": "code",
                        "ignore_preset": "javascript",
                    }
                )
                found_types.discard("js")
                found_types.discard("jsx")

            # Add remaining types
            for ext in found_types:
                info = type_patterns[ext]
                source: dict[str, str | None] = {
                    "path": ".",
                    "glob": info["glob"],
                    "type": info["type"],
                }
                if info["preset"]:
                    source["ignore_preset"] = info["preset"]
                sources.append(source)
        else:
            # Fallback: index all text files
            sources.append(
                {
                    "path": ".",
                    "glob": "**/*",
                    "type": None,
                }
            )

        # Common patterns to always ignore (use **/ prefix for nested directories)
        common_ignores = [
            "**/.git/**",
            "**/.tox/**",
            "**/.cache/**",
            "**/*.egg-info/**",
            "**/.eggs/**",
            "**/.DS_Store",
            "**/site-packages/**",
            "**/dist/**",
            "**/build/**",
        ]

        # Build config YAML
        config_content = """# Gundog configuration - auto-generated
# Edit sources to customize what gets indexed

sources:
"""
        for src in sources:
            config_content += f'  - path: "{src["path"]}"\n'
            config_content += f'    glob: "{src["glob"]}"\n'
            if src.get("type"):
                config_content += f"    type: {src['type']}\n"
            if src.get("ignore_preset"):
                config_content += f"    ignore_preset: {src['ignore_preset']}\n"
            config_content += "    use_gitignore: true\n"
            config_content += "    ignore:\n"
            for pattern in common_ignores:
                config_content += f'      - "{pattern}"\n'
            config_content += "\n"

        config_content += """embedding:
  model: BAAI/bge-small-en-v1.5
  enable_onnx: true
  threads: 2  # CPU threads (increase for faster indexing, decrease if system slows)

storage:
  use_hnsw: true
  path: .gundog/index

chunking:
  enabled: true
  max_tokens: 512
  overlap_tokens: 50
"""
        config_path.write_text(config_content)
        return config_path

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

        embedding = EmbeddingConfig(**data.get("embedding", {}))
        storage = StorageConfig(**data.get("storage", {}))
        graph = GraphConfig(**data.get("graph", {}))
        hybrid = HybridConfig(**data.get("hybrid", {}))
        chunking = ChunkingConfig(**data.get("chunking", {}))
        recency = RecencyConfig(**data.get("recency", {}))

        return cls(
            sources=sources,
            embedding=embedding,
            storage=storage,
            graph=graph,
            hybrid=hybrid,
            chunking=chunking,
            recency=recency,
        )
