"""File discovery, embedding, and index management."""

import hashlib
from fnmatch import fnmatch
from pathlib import Path
from typing import Any

from gundog._bm25 import BM25Index
from gundog._chunker import chunk_text, make_chunk_id, parse_chunk_id
from gundog._config import GundogConfig, SourceConfig
from gundog._embedder import Embedder
from gundog._graph import SimilarityGraph
from gundog._store import create_store
from gundog._templates import get_exclusion_patterns


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

        # Load existing index if present
        self.store.load()
        self.graph.load()
        self.bm25.load()

    def _should_exclude(self, path: Path, excludes: list[str]) -> bool:
        """Check if path matches any exclude pattern."""
        path_str = str(path)
        return any(fnmatch(path_str, pattern) for pattern in excludes)

    def _hash_content(self, content: str) -> str:
        """Compute SHA256 hash of content."""
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def _scan_source(self, source: SourceConfig) -> list[Path]:
        """Scan a single source directory for matching files."""
        source_path = Path(source.path)
        if not source_path.exists():
            print(f"Warning: Source path does not exist: {source.path}")
            return []

        # Combine template patterns with custom excludes
        excludes = list(source.exclude)
        if source.exclusion_template:
            excludes.extend(get_exclusion_patterns(source.exclusion_template))

        files = []
        for file_path in source_path.glob(source.glob):
            if file_path.is_file() and not self._should_exclude(file_path, excludes):
                files.append(file_path)

        return files

    def _needs_reindex(self, file_path: Path) -> bool:
        """
        Check if file needs reindexing.

        Uses hybrid mtime + content hash approach:
        1. If mtime unchanged -> skip (fast path)
        2. If mtime changed -> check content hash (reliable)
        """
        file_id = str(file_path)

        # With chunking, files are stored as file_path#chunk_N
        # Check for the file itself or its first chunk
        result = self.store.get(file_id)
        if result is None and self.config.chunking.enabled:
            result = self.store.get(make_chunk_id(file_id, 0))

        if result is None:
            return True  # New file

        _, metadata = result

        # Fast path: mtime unchanged
        current_mtime = file_path.stat().st_mtime
        if current_mtime == metadata.get("mtime"):
            return False

        # Mtime changed - verify with content hash
        content = file_path.read_text(encoding="utf-8")
        current_hash = self._hash_content(content)

        return current_hash != metadata.get("content_hash")

    def index(self, rebuild: bool = False) -> dict[str, Any]:
        """
        Index all configured sources.

        Args:
            rebuild: If True, reindex everything regardless of cache

        Returns:
            Summary dict with counts of indexed/skipped/removed files
        """
        summary: dict[str, Any] = {
            "files_total": 0,
            "files_indexed": 0,
            "files_skipped": 0,
            "files_removed": 0,
            "chunks_indexed": 0,
        }

        all_files: dict[str, tuple[Path, str | None]] = {}  # path_str -> (Path, type)

        # Scan all sources
        for source in self.config.sources:
            files = self._scan_source(source)
            for file_path in files:
                all_files[str(file_path)] = (file_path, source.type)

        summary["files_total"] = len(all_files)
        print(f"Found {len(all_files)} files")

        # Remove files (and their chunks) no longer present
        existing_ids = set(self.store.all_ids())
        current_file_ids = set(all_files.keys())

        # For chunked files, we need to remove all chunks when the file is gone
        removed_count = 0
        for existing_id in existing_ids:
            parent_file, _ = parse_chunk_id(existing_id)
            if parent_file not in current_file_ids:
                self.store.delete(existing_id)
                removed_count += 1

        summary["files_removed"] = removed_count
        if removed_count:
            print(f"Removed {removed_count} entries from index")

        # Index new/changed files
        to_index: list[tuple[str, Path, str | None]] = []
        for file_id, (file_path, file_type) in all_files.items():
            if rebuild or self._needs_reindex(file_path):
                to_index.append((file_id, file_path, file_type))
            else:
                summary["files_skipped"] += 1

        summary["files_indexed"] = len(to_index)

        if to_index:
            print(f"Indexing {len(to_index)} files...")

            # Prepare all texts for embedding (files or chunks)
            # (id, text, path, type, start_line, end_line)
            embed_items: list[tuple[str, str, Path, str | None, int | None, int | None]] = []

            for file_id, file_path, file_type in to_index:
                try:
                    content = file_path.read_text(encoding="utf-8")

                    if self.config.chunking.enabled:
                        # Remove old chunks for this file before re-chunking
                        for existing_id in list(self.store.all_ids()):
                            parent, _ = parse_chunk_id(existing_id)
                            if parent == file_id:
                                self.store.delete(existing_id)

                        # Split into chunks
                        chunks = chunk_text(
                            content,
                            max_tokens=self.config.chunking.max_tokens,
                            overlap_tokens=self.config.chunking.overlap_tokens,
                        )

                        for chunk in chunks:
                            chunk_id = make_chunk_id(file_id, chunk.index)
                            chunk_text_with_context = (
                                f"Path: {file_path}\n"
                                f"Chunk {chunk.index + 1}/{len(chunks)}\n\n"
                                f"{chunk.text}"
                            )
                            # Calculate line numbers for this chunk
                            start_line = content[: chunk.start_char].count("\n") + 1
                            end_line = content[: chunk.end_char].count("\n") + 1
                            embed_items.append(
                                (
                                    chunk_id,
                                    chunk_text_with_context,
                                    file_path,
                                    file_type,
                                    start_line,
                                    end_line,
                                )
                            )
                    else:
                        # Whole-file embedding (no line range for whole files)
                        full_content = f"Path: {file_path}\n\n{content}"
                        embed_items.append(
                            (file_id, full_content, file_path, file_type, None, None)
                        )

                except Exception as e:
                    print(f"Warning: Could not read {file_path}: {e}")

            if embed_items:
                # Batch embed
                texts = [item[1] for item in embed_items]
                embeddings = self.embedder.embed_batch(texts, show_progress=True)

                # Store embeddings with metadata
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

                        # Add chunk-specific metadata
                        if chunk_idx is not None:
                            file_meta["parent_file"] = parent_file
                            file_meta["chunk_index"] = chunk_idx
                            if start_line is not None:
                                file_meta["start_line"] = start_line
                                file_meta["end_line"] = end_line

                        self.store.upsert(item_id, embedding, file_meta)
                        summary["chunks_indexed"] += 1
                    except Exception as e:
                        print(f"Warning: Could not index {item_id}: {e}")

        # Only rebuild graph/BM25 if something changed
        needs_rebuild = rebuild or summary["files_indexed"] > 0 or summary["files_removed"] > 0

        if needs_rebuild:
            # Rebuild similarity graph
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
        else:
            print("No changes, skipping graph rebuild.")

        # Build BM25 index for hybrid search
        if self.config.hybrid.enabled and needs_rebuild:
            print("Building BM25 index...")
            documents: dict[str, str] = {}

            if self.config.chunking.enabled:
                # For chunked mode, index each chunk separately
                for item_id in self.store.all_ids():
                    result = self.store.get(item_id)
                    if result:
                        _, meta = result
                        parent_file = meta.get("parent_file", item_id)
                        chunk_idx = meta.get("chunk_index")

                        try:
                            file_path = Path(parent_file)
                            if file_path.exists():
                                content = file_path.read_text(encoding="utf-8")
                                if chunk_idx is not None:
                                    # Re-chunk to get specific chunk text
                                    chunks = chunk_text(
                                        content,
                                        max_tokens=self.config.chunking.max_tokens,
                                        overlap_tokens=self.config.chunking.overlap_tokens,
                                    )
                                    if chunk_idx < len(chunks):
                                        documents[item_id] = (
                                            f"{file_path}\n{chunks[chunk_idx].text}"
                                        )
                                else:
                                    documents[item_id] = f"{file_path}\n{content}"
                        except Exception:
                            pass
            else:
                # Whole-file mode
                for file_id in self.store.all_ids():
                    try:
                        file_path = Path(file_id)
                        if file_path.exists():
                            content = file_path.read_text(encoding="utf-8")
                            documents[file_id] = f"{file_path}\n{content}"
                    except Exception:
                        pass

            self.bm25.build(documents)

        # Save only if changes were made
        if needs_rebuild:
            self.store.save()
            self.graph.save()
            if self.config.hybrid.enabled:
                self.bm25.save()

        # Print summary
        if self.config.chunking.enabled:
            print(
                f"Done: {summary['files_indexed']} files ({summary['chunks_indexed']} chunks), "
                f"{summary['files_skipped']} unchanged, {summary['files_removed']} removed"
            )
        else:
            print(
                f"Done: {summary['files_indexed']} files indexed, "
                f"{summary['files_skipped']} unchanged, {summary['files_removed']} removed"
            )
        return summary
