"""File discovery, embedding, and index management."""

import hashlib
import subprocess
from pathlib import Path
from typing import Any

import pathspec

from gundog._bm25 import BM25Index
from gundog._chunker import Chunk, chunk_text, make_chunk_id, parse_chunk_id
from gundog._config import GundogConfig, SourceConfig
from gundog._embedder import create_embedder
from gundog._git import get_git_info
from gundog._graph import SimilarityGraph
from gundog._store import create_store
from gundog._templates import get_ignore_patterns
from gundog._tfidf import LineTFIDFIndex


class Indexer:
    """
    Handles file discovery, embedding, and index management.

    Responsibilities:
    - Scan source directories for files matching glob patterns
    - Compute embeddings for new/changed files
    - Build similarity graph
    - Build BM25 index for hybrid search
    - Persist index to disk
    """

    def __init__(self, config: GundogConfig):
        self.config = config
        self.embedder = create_embedder(
            config.embedding.model,
            enable_onnx=config.embedding.enable_onnx,
            threads=config.embedding.threads,
        )
        self.store = create_store(config.storage.use_hnsw, config.storage.path)
        self.graph = SimilarityGraph(Path(config.storage.path) / "graph.json")
        self.bm25 = BM25Index(Path(config.storage.path) / "bm25.pkl")
        self.tfidf = LineTFIDFIndex(Path(config.storage.path) / "line_tfidf.pkl")

        self.store.load()
        self.graph.load()
        self.bm25.load()
        self.tfidf.load()

    def _should_ignore(self, path: Path, patterns: list[str]) -> bool:
        """Check if path matches any ignore pattern using gitignore-style matching.

        Note: Python 3.13+ has Path.full_match() which handles ** patterns natively.
        We use pathspec for 3.12 compatibility.
        """
        if not patterns:
            return False
        spec = pathspec.PathSpec.from_lines("gitwildmatch", patterns)
        return spec.match_file(path)

    def _get_git_blob_hash(self, file_path: Path) -> str | None:
        """Get git blob hash for a file. Returns None if not tracked by git."""
        try:
            result = subprocess.run(
                ["git", "ls-files", "-s", file_path.name],
                cwd=file_path.parent,
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                # Output format: "100644 <blob_hash> 0\t<filename>"
                parts = result.stdout.strip().split()
                if len(parts) >= 2:
                    return parts[1]  # blob hash
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            pass
        return None

    def _get_git_last_modified(self, file_path: Path) -> int | None:
        """Get Unix timestamp of last commit that modified this file."""
        try:
            result = subprocess.run(
                ["git", "log", "-1", "--format=%ct", "--", file_path.name],
                cwd=file_path.parent,
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                return int(result.stdout.strip())
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError, ValueError):
            pass
        return None

    def _is_text_file(self, path: Path, sample_size: int = 8192) -> bool:
        """Check if a file is text (not binary)."""
        try:
            with open(path, "rb") as f:
                chunk = f.read(sample_size)
            # Check for null bytes (binary indicator)
            if b"\x00" in chunk:
                return False
            # Try to decode as UTF-8
            chunk.decode("utf-8")
            return True
        except (OSError, UnicodeDecodeError):
            return False

    def _parse_gitignore(self, gitignore_path: Path) -> list[str]:
        """Parse .gitignore file and convert to glob patterns."""
        if not gitignore_path.exists():
            return []

        patterns: list[str] = []
        try:
            for line in gitignore_path.read_text().splitlines():
                line = line.strip()
                # Skip empty lines and comments
                if not line or line.startswith("#"):
                    continue
                # Convert gitignore patterns to glob patterns
                if line.startswith("/"):
                    # Rooted pattern - relative to gitignore location
                    patterns.append(f"{gitignore_path.parent}{line}")
                elif "/" in line and not line.endswith("/"):
                    # Path pattern
                    patterns.append(f"**/{line}")
                else:
                    # Simple pattern - match anywhere
                    pattern = line.rstrip("/")
                    patterns.append(f"**/{pattern}")
                    patterns.append(f"**/{pattern}/**")
        except (OSError, UnicodeDecodeError):
            pass  # Silently ignore unreadable .gitignore files

        return patterns

    def _hash_content(self, content: str) -> str:
        """Compute SHA256 hash of content."""
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def _scan_source(self, source: SourceConfig) -> list[Path]:
        """Scan a single source directory for matching files."""
        source_path = Path(source.path)
        if not source_path.exists():
            print(f"Warning: Source path does not exist: {source.path}")
            return []

        # Collect all ignore patterns
        patterns = list(source.ignore)

        # Add preset patterns
        if source.ignore_preset:
            patterns.extend(get_ignore_patterns(source.ignore_preset))

        # Add gitignore patterns if enabled
        if source.use_gitignore:
            gitignore_path = source_path / ".gitignore"
            patterns.extend(self._parse_gitignore(gitignore_path))

        files = []
        for file_path in source_path.glob(source.glob):
            if (
                file_path.is_file()
                and not self._should_ignore(file_path, patterns)
                and self._is_text_file(file_path)
            ):
                files.append(file_path)

        return files

    def _needs_reindex(self, file_path: Path) -> bool:
        """Check if file needs reindexing. Uses git blob hash if available, else mtime+hash."""
        file_id = str(file_path)

        result = self.store.get(file_id)
        if result is None and self.config.chunking.enabled:
            result = self.store.get(make_chunk_id(file_id, 0))

        if result is None:
            return True

        _, metadata = result

        # Try git blob hash first (fast, reliable)
        git_blob = self._get_git_blob_hash(file_path)
        if git_blob is not None:
            stored_blob = metadata.get("git_blob_hash")
            return git_blob != stored_blob

        # Fall back to mtime + content hash for non-git files
        current_mtime = file_path.stat().st_mtime
        if current_mtime == metadata.get("mtime"):
            return False

        content = file_path.read_text(encoding="utf-8")
        current_hash = self._hash_content(content)
        return current_hash != metadata.get("content_hash")

    def _scan_all_sources(self) -> dict[str, tuple[Path, str | None]]:
        """Scan all configured sources and return file mapping."""
        all_files: dict[str, tuple[Path, str | None]] = {}
        for source in self.config.sources:
            files = self._scan_source(source)
            for file_path in files:
                all_files[str(file_path)] = (file_path, source.type)
        return all_files

    def _remove_stale_entries(self, current_file_ids: set[str]) -> int:
        """Remove entries for files that no longer exist."""
        existing_ids = set(self.store.all_ids())
        removed_count = 0

        for existing_id in existing_ids:
            parent_file, _ = parse_chunk_id(existing_id)
            if parent_file not in current_file_ids:
                self.store.delete(existing_id)
                removed_count += 1

        return removed_count

    def _prepare_chunks(
        self, file_id: str, file_path: Path, content: str, file_type: str | None
    ) -> list[tuple[str, str, Path, str | None, int | None, int | None]]:
        """Prepare chunks for a file, removing old chunks first."""
        items: list[tuple[str, str, Path, str | None, int | None, int | None]] = []

        # Remove old chunks
        for existing_id in list(self.store.all_ids()):
            parent, _ = parse_chunk_id(existing_id)
            if parent == file_id:
                self.store.delete(existing_id)

        chunks: list[Chunk] = chunk_text(
            content,
            max_tokens=self.config.chunking.max_tokens,
            overlap_tokens=self.config.chunking.overlap_tokens,
        )

        for chunk in chunks:
            chunk_id = make_chunk_id(file_id, chunk.index)
            chunk_text_with_context = (
                f"Path: {file_path}\nChunk {chunk.index + 1}/{len(chunks)}\n\n{chunk.text}"
            )
            start_line = content[: chunk.start_char].count("\n") + 1
            end_line = content[: chunk.end_char].count("\n") + 1
            items.append(
                (chunk_id, chunk_text_with_context, file_path, file_type, start_line, end_line)
            )

        return items

    def _prepare_embed_items(
        self, to_index: list[tuple[str, Path, str | None]]
    ) -> list[tuple[str, str, Path, str | None, int | None, int | None]]:
        """Prepare all items (files or chunks) for embedding."""
        embed_items: list[tuple[str, str, Path, str | None, int | None, int | None]] = []

        for file_id, file_path, file_type in to_index:
            try:
                content = file_path.read_text(encoding="utf-8")

                if self.config.chunking.enabled:
                    embed_items.extend(
                        self._prepare_chunks(file_id, file_path, content, file_type)
                    )
                else:
                    full_content = f"Path: {file_path}\n\n{content}"
                    embed_items.append((file_id, full_content, file_path, file_type, None, None))

            except Exception as e:
                print(f"Warning: Could not read {file_path}: {e}")

        return embed_items

    def _embed_and_store(
        self, embed_items: list[tuple[str, str, Path, str | None, int | None, int | None]]
    ) -> int:
        """Batch embed items and store with metadata. Returns count stored."""
        if not embed_items:
            return 0

        texts = [item[1] for item in embed_items]
        embeddings = self.embedder.embed_batch(texts, show_progress=True)

        stored = 0
        for (item_id, _, file_path, file_type, start_line, end_line), embedding in zip(
            embed_items, embeddings, strict=True
        ):
            try:
                content = file_path.read_text(encoding="utf-8")
                parent_file, chunk_idx = parse_chunk_id(item_id)

                file_meta: dict[str, Any] = {
                    "type": file_type,
                    "mtime": file_path.stat().st_mtime,
                    "content_hash": self._hash_content(content),
                }

                # Store git blob hash for faster incremental indexing
                git_blob = self._get_git_blob_hash(file_path)
                if git_blob:
                    file_meta["git_blob_hash"] = git_blob

                # Store git last modified timestamp for recency scoring
                git_mtime = self._get_git_last_modified(file_path)
                if git_mtime:
                    file_meta["git_last_modified"] = git_mtime

                git_info = get_git_info(file_path)
                if git_info is not None:
                    file_meta["git_url"] = git_info.remote_url
                    file_meta["git_branch"] = git_info.branch
                    file_meta["git_relative_path"] = git_info.relative_path

                if chunk_idx is not None:
                    file_meta["parent_file"] = parent_file
                    file_meta["chunk_index"] = chunk_idx
                    if start_line is not None:
                        file_meta["start_line"] = start_line
                        file_meta["end_line"] = end_line

                self.store.upsert(item_id, embedding, file_meta)
                stored += 1
            except Exception as e:
                print(f"Warning: Could not index {item_id}: {e}")

        return stored

    def _build_graph(self) -> None:
        """Build similarity graph from stored vectors."""
        print("Building similarity graph...")
        vectors = self.store.all_vectors()
        metadata: dict[str, dict[str, Any]] = {}

        for vec_id in vectors:
            result = self.store.get(vec_id)
            if result is not None:
                metadata[vec_id] = result[1]

        self.graph.build(
            vectors=vectors,
            metadata=metadata,
            threshold=self.config.graph.similarity_threshold,
        )

    def _build_bm25(self) -> None:
        """Build BM25 index for hybrid search."""
        print("Building BM25 index...")
        documents: dict[str, str] = {}

        for item_id in self.store.all_ids():
            result = self.store.get(item_id)
            if not result:
                continue

            _, meta = result
            parent_file = meta.get("parent_file", item_id)
            chunk_idx = meta.get("chunk_index")

            try:
                file_path = Path(parent_file)
                if not file_path.exists():
                    continue

                content = file_path.read_text(encoding="utf-8")

                if chunk_idx is not None:
                    chunks = chunk_text(
                        content,
                        max_tokens=self.config.chunking.max_tokens,
                        overlap_tokens=self.config.chunking.overlap_tokens,
                    )
                    if chunk_idx < len(chunks):
                        documents[item_id] = f"{file_path}\n{chunks[chunk_idx].text}"
                else:
                    documents[item_id] = f"{file_path}\n{content}"
            except (OSError, UnicodeDecodeError):
                continue  # Skip files that can't be read

        self.bm25.build(documents)

    def _build_tfidf(self) -> None:
        """Build per-line TF-IDF index for fine-grained ranking."""
        if not self.config.chunking.enabled:
            # TF-IDF per-line only makes sense with chunking
            return

        print("Building TF-IDF per-line index...")
        chunks: dict[str, tuple[str, int]] = {}

        for item_id in self.store.all_ids():
            result = self.store.get(item_id)
            if not result:
                continue

            _, meta = result
            parent_file = meta.get("parent_file", item_id)
            chunk_idx = meta.get("chunk_index")
            start_line = meta.get("start_line", 1)

            if chunk_idx is None:
                # Not a chunk, skip
                continue

            try:
                file_path = Path(parent_file)
                if not file_path.exists():
                    continue

                content = file_path.read_text(encoding="utf-8")
                chunk_list = chunk_text(
                    content,
                    max_tokens=self.config.chunking.max_tokens,
                    overlap_tokens=self.config.chunking.overlap_tokens,
                )
                if chunk_idx < len(chunk_list):
                    chunks[item_id] = (chunk_list[chunk_idx].text, start_line)
            except (OSError, UnicodeDecodeError):
                continue  # Skip files that can't be read

        self.tfidf.build(chunks)

    def _save_all(self) -> None:
        """Save store, graph, BM25, and TF-IDF indexes."""
        self.store.save()
        self.graph.save()
        if self.config.hybrid.enabled:
            self.bm25.save()
        if self.config.chunking.enabled:
            self.tfidf.save()

    def index(self, rebuild: bool = False) -> dict[str, Any]:
        """
        Index all configured sources.

        Args:
            rebuild: If True, reindex everything regardless of cache

        Returns:
            Summary dict with counts of indexed/skipped/removed files
        """
        # Scan sources
        all_files = self._scan_all_sources()
        print(f"Found {len(all_files)} files")

        # Remove stale entries
        removed_count = self._remove_stale_entries(set(all_files.keys()))
        if removed_count:
            print(f"Removed {removed_count} entries from index")

        # Determine what needs indexing
        to_index: list[tuple[str, Path, str | None]] = []
        skipped = 0

        for file_id, (file_path, file_type) in all_files.items():
            if rebuild or self._needs_reindex(file_path):
                to_index.append((file_id, file_path, file_type))
            else:
                skipped += 1

        # Index files
        chunks_indexed = 0
        if to_index:
            print(f"Indexing {len(to_index)} files...")
            embed_items = self._prepare_embed_items(to_index)
            chunks_indexed = self._embed_and_store(embed_items)

        # Rebuild indices if needed
        needs_rebuild = rebuild or len(to_index) > 0 or removed_count > 0

        if needs_rebuild:
            self._build_graph()
            if self.config.hybrid.enabled:
                self._build_bm25()
            if self.config.chunking.enabled:
                self._build_tfidf()
            self._save_all()
        else:
            print("No changes, skipping graph rebuild.")

        # Summary
        summary = {
            "files_total": len(all_files),
            "files_indexed": len(to_index),
            "files_skipped": skipped,
            "files_removed": removed_count,
            "chunks_indexed": chunks_indexed,
        }

        if self.config.chunking.enabled:
            print(
                f"Done: {summary['files_indexed']} files ({chunks_indexed} chunks), "
                f"{skipped} unchanged, {removed_count} removed"
            )
        else:
            print(
                f"Done: {summary['files_indexed']} files indexed, "
                f"{skipped} unchanged, {removed_count} removed"
            )

        return summary
