"""File discovery, embedding, and index management."""

import hashlib
from fnmatch import fnmatch
from pathlib import Path
from typing import Any

from gundog._bm25 import BM25Index
from gundog._chunker import Chunk, chunk_text, make_chunk_id, parse_chunk_id
from gundog._config import GundogConfig, SourceConfig
from gundog._embedder import Embedder
from gundog._git import get_git_info
from gundog._graph import SimilarityGraph
from gundog._store import create_store
from gundog._templates import get_ignore_patterns


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
        self.embedder = Embedder(config.embedding.model)
        self.store = create_store(config.storage.backend, config.storage.path)
        self.graph = SimilarityGraph(Path(config.storage.path) / "graph.json")
        self.bm25 = BM25Index(Path(config.storage.path) / "bm25.pkl")

        self.store.load()
        self.graph.load()
        self.bm25.load()

    def _should_ignore(self, path: Path, patterns: list[str]) -> bool:
        """Check if path matches any ignore pattern."""
        path_str = str(path)
        return any(fnmatch(path_str, pattern) for pattern in patterns)

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
        except Exception:
            pass

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
            if file_path.is_file() and not self._should_ignore(file_path, patterns):
                files.append(file_path)

        return files

    def _needs_reindex(self, file_path: Path) -> bool:
        """Check if file needs reindexing using mtime + content hash."""
        file_id = str(file_path)

        result = self.store.get(file_id)
        if result is None and self.config.chunking.enabled:
            result = self.store.get(make_chunk_id(file_id, 0))

        if result is None:
            return True

        _, metadata = result

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

        for id in vectors:
            result = self.store.get(id)
            if result is not None:
                metadata[id] = result[1]

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
            except Exception:
                pass

        self.bm25.build(documents)

    def _save_all(self) -> None:
        """Save store, graph, and BM25 index."""
        self.store.save()
        self.graph.save()
        if self.config.hybrid.enabled:
            self.bm25.save()

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
