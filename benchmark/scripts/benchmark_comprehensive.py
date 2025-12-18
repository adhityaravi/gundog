#!/usr/bin/env python3
"""
Comprehensive Gundog Benchmark

Tests:
- File-level accuracy (did we find the right file?)
- Chunk-level accuracy (did we find the right chunk/section?)
- Graph expansion quality (did related files get discovered?)
- Performance (index time, query time)

Configurations:
- Models: bge-small, bge-base
- Storage: numpy, hnsw
- Embedder: sentence-transformers, onnx
"""

import json
import shutil
import sys
import time
from dataclasses import dataclass, field
from io import StringIO
from pathlib import Path

# Noisy queries - realistic user queries with typos, vague terms, natural language
QUERIES = [
    # Authentication & Credentials - with noise
    {
        "q": "how do arr apps share api keys between each other",
        "expected_file": "adr-002-cross-app-auth",
        "expected_code": ["_reconcilers.py", "_arr_client.py"],
        "expected_chunk_keywords": ["api_key", "credential", "authentication"],
        "category": "auth",
    },
    {
        "q": "qbittorrent password storage and hashing mechanism",
        "expected_file": "adr-002-cross-app-auth",
        "expected_code": ["_reconcilers.py"],
        "expected_chunk_keywords": ["password", "hash", "PBKDF2"],
        "category": "auth",
    },
    {
        "q": "juju secrets rotation for api credentials",
        "expected_file": "adr-002-secret-management",
        "expected_code": [],
        "expected_chunk_keywords": ["secret", "rotation", "juju"],
        "category": "auth",
    },
    # VPN & Networking - with noise
    {
        "q": "how does the vpn killswitch prevent leaks",
        "expected_file": "adr-004-vpn-kill-switch",
        "expected_code": ["_kill_switch.py"],
        "expected_chunk_keywords": ["kill", "switch", "network", "policy"],
        "category": "vpn",
    },
    {
        "q": "gluetun container network firewall rules",
        "expected_file": "adr-004-vpn-kill-switch",
        "expected_code": ["_kill_switch.py"],
        "expected_chunk_keywords": ["gluetun", "firewall", "egress"],
        "category": "vpn",
    },
    {
        "q": "download client traffic routing through gateway",
        "expected_file": "adr-003-download-client-egress",
        "expected_code": [],
        "expected_chunk_keywords": ["egress", "gateway", "routing"],
        "category": "vpn",
    },
    {
        "q": "vpn gateway provider interface charm integration",
        "expected_file": "adr-007-vpn-gateway",
        "expected_code": [],
        "expected_chunk_keywords": ["gateway", "provider", "interface"],
        "category": "vpn",
    },
    # Storage - with noise
    {
        "q": "pvc patching for statefulset volumes kubernetes",
        "expected_file": "adr-003-pvc-patching",
        "expected_code": ["_storage.py"],
        "expected_chunk_keywords": ["pvc", "statefulset", "patch", "volume"],
        "category": "storage",
    },
    {
        "q": "shared storage hardlinks between radarr sonarr",
        "expected_file": "adr-001-shared-pvc",
        "expected_code": ["_media_storage.py"],
        "expected_chunk_keywords": ["hardlink", "shared", "pvc"],
        "category": "storage",
    },
    {
        "q": "linuxserver container PUID PGID file ownership",
        "expected_file": "adr-005-charmarr-storage",
        "expected_code": [],
        "expected_chunk_keywords": ["PUID", "PGID", "ownership"],
        "category": "storage",
    },
    # Prowlarr & Indexer - with noise
    {
        "q": "prowlarr app registration and sync level config",
        "expected_file": "adr-008-prowlarr",
        "expected_code": ["_prowlarr_client.py", "_reconcilers.py"],
        "expected_chunk_keywords": ["prowlarr", "registration", "sync"],
        "category": "prowlarr",
    },
    {
        "q": "media indexer interface data model",
        "expected_file": "adr-003-media-indexer",
        "expected_code": ["_media_indexer.py"],
        "expected_chunk_keywords": ["indexer", "interface", "data"],
        "category": "prowlarr",
    },
    # Download Client - with noise
    {
        "q": "download client qbit vs sabnzbd auth differences",
        "expected_file": "adr-004-download-client",
        "expected_code": ["_download_client.py"],
        "expected_chunk_keywords": ["download", "client", "authentication"],
        "category": "download",
    },
    {
        "q": "torrent usenet client type distinction",
        "expected_file": "adr-004-download-client",
        "expected_code": ["_download_client.py"],
        "expected_chunk_keywords": ["torrent", "usenet", "type"],
        "category": "download",
    },
    # Reconciliation - with noise
    {
        "q": "aggressive vs gentle reconciliation strategy decision",
        "expected_file": "adr-003-reconciliation",
        "expected_code": ["_reconcilers.py"],
        "expected_chunk_keywords": ["reconcil", "aggressive", "strategy"],
        "category": "reconcile",
    },
    {
        "q": "user quality profiles should not be deleted",
        "expected_file": "adr-003-reconciliation",
        "expected_code": [],
        "expected_chunk_keywords": ["quality", "profile", "preserve"],
        "category": "reconcile",
    },
    # API Clients - with noise
    {
        "q": "base arr api client http request handling",
        "expected_file": "_base_client.py",
        "expected_code": ["_base_client.py"],
        "expected_chunk_keywords": ["http", "request", "api"],
        "category": "api",
    },
    {
        "q": "get download clients method arr api",
        "expected_file": "_arr_client.py",
        "expected_code": ["_arr_client.py"],
        "expected_chunk_keywords": ["download", "client", "get"],
        "category": "api",
    },
    # K8s - with noise
    {
        "q": "network policy egress cluster cidr whitelist",
        "expected_file": "_kill_switch.py",
        "expected_code": ["_kill_switch.py"],
        "expected_chunk_keywords": ["network", "policy", "egress", "cidr"],
        "category": "k8s",
    },
    {
        "q": "lightkube statefulset volume patch function",
        "expected_file": "_storage.py",
        "expected_code": ["_storage.py"],
        "expected_chunk_keywords": ["lightkube", "statefulset", "patch"],
        "category": "k8s",
    },
]


@dataclass
class Config:
    name: str
    model: str
    storage_backend: str
    embedding_backend: str


@dataclass
class QueryResult:
    query: str
    category: str
    # File-level metrics
    file_found: bool
    file_rank: int  # -1 if not found
    # Chunk-level metrics
    chunk_keyword_hits: int
    chunk_keyword_total: int
    # Graph expansion metrics
    code_files_expected: int
    code_files_found: int
    related_files_count: int
    # Performance
    query_time_ms: float


@dataclass
class BenchmarkResult:
    config: Config
    # Accuracy
    file_accuracy: float
    file_mrr: float  # Mean Reciprocal Rank
    chunk_keyword_recall: float
    graph_code_recall: float
    # Performance
    index_time_s: float
    first_query_ms: float
    avg_query_ms: float
    # Details
    query_results: list[QueryResult] = field(default_factory=list)


CONFIGS = [
    Config("small_numpy_st", "BAAI/bge-small-en-v1.5", "numpy", "sentence-transformers"),
    Config("small_hnsw_st", "BAAI/bge-small-en-v1.5", "hnsw", "sentence-transformers"),
    Config("small_hnsw_onnx", "BAAI/bge-small-en-v1.5", "hnsw", "onnx"),
    Config("base_hnsw_st", "BAAI/bge-base-en-v1.5", "hnsw", "sentence-transformers"),
    Config("base_hnsw_onnx", "BAAI/bge-base-en-v1.5", "hnsw", "onnx"),
]


def run_benchmark(
    cfg: Config,
    source_dirs: list[tuple[Path, str]],
) -> BenchmarkResult:
    """Run benchmark for a single configuration."""
    from gundog._config import (
        ChunkingConfig,
        EmbeddingConfig,
        GraphConfig,
        GundogConfig,
        HybridConfig,
        SourceConfig,
        StorageConfig,
    )
    from gundog._indexer import Indexer
    from gundog._query import QueryEngine

    index_path = f"/tmp/gundog_bench_{cfg.name}"

    # Build sources
    sources = []
    for src_dir, src_type in source_dirs:
        if src_type == "adr":
            sources.append(SourceConfig(
                path=str(src_dir),
                glob="**/*.md",
                type="adr",
                ignore=["**/README.md"],
            ))
        else:
            sources.append(SourceConfig(
                path=str(src_dir),
                glob="**/*.py",
                type="code",
                ignore=["**/__pycache__/**", "**/.venv/**", "**/__init__.py", "**/_version.py", "**/test_*.py", "**/conftest.py"],
            ))

    # Build config
    gundog_cfg = GundogConfig(
        sources=sources,
        embedding=EmbeddingConfig(model=cfg.model, backend=cfg.embedding_backend),
        storage=StorageConfig(backend=cfg.storage_backend, path=index_path),
        hybrid=HybridConfig(enabled=True),
        chunking=ChunkingConfig(enabled=True, max_tokens=512, overlap_tokens=50),
        graph=GraphConfig(similarity_threshold=0.65, max_expand_depth=2, expand_threshold=0.60),
    )

    # Clean index
    idx_path = Path(index_path)
    if idx_path.exists():
        shutil.rmtree(idx_path)
    idx_path.mkdir(parents=True)

    # Suppress output
    old_stdout = sys.stdout
    sys.stdout = StringIO()

    # Index
    index_start = time.perf_counter()
    indexer = Indexer(gundog_cfg)
    indexer.index(rebuild=True)
    index_time = time.perf_counter() - index_start

    sys.stdout = old_stdout

    # Query engine
    engine = QueryEngine(gundog_cfg)

    query_results = []
    query_times = []

    for i, q_data in enumerate(QUERIES):
        query = q_data["q"]
        expected_file = q_data["expected_file"]
        expected_code = q_data["expected_code"]
        expected_keywords = q_data["expected_chunk_keywords"]

        start = time.perf_counter()
        result = engine.query(query, top_k=10, expand=True, expand_depth=2, min_score=0.25)
        elapsed_ms = (time.perf_counter() - start) * 1000
        query_times.append(elapsed_ms)

        # File-level accuracy
        file_found = False
        file_rank = -1
        for j, r in enumerate(result.direct[:10]):
            if expected_file in r["path"]:
                file_found = True
                file_rank = j + 1
                break

        # Chunk-level accuracy (keyword presence in top result content)
        chunk_hits = 0
        if result.direct:
            top_content = result.direct[0].get("content", "").lower()
            for kw in expected_keywords:
                if kw.lower() in top_content:
                    chunk_hits += 1

        # Graph expansion accuracy (did we find expected code files?)
        all_files = [Path(r["path"]).name for r in result.direct + result.related]
        code_found = sum(1 for code_file in expected_code if any(code_file in f for f in all_files))

        query_results.append(QueryResult(
            query=query,
            category=q_data["category"],
            file_found=file_found,
            file_rank=file_rank,
            chunk_keyword_hits=chunk_hits,
            chunk_keyword_total=len(expected_keywords),
            code_files_expected=len(expected_code),
            code_files_found=code_found,
            related_files_count=len(result.related),
            query_time_ms=elapsed_ms,
        ))

    # Calculate aggregate metrics
    file_accuracy = sum(1 for r in query_results if r.file_found) / len(query_results)

    # MRR (Mean Reciprocal Rank)
    mrr_sum = sum(1/r.file_rank for r in query_results if r.file_rank > 0)
    file_mrr = mrr_sum / len(query_results)

    # Chunk keyword recall
    total_kw_hits = sum(r.chunk_keyword_hits for r in query_results)
    total_kw = sum(r.chunk_keyword_total for r in query_results)
    chunk_recall = total_kw_hits / total_kw if total_kw > 0 else 0

    # Graph code file recall
    total_code_expected = sum(r.code_files_expected for r in query_results)
    total_code_found = sum(r.code_files_found for r in query_results)
    graph_recall = total_code_found / total_code_expected if total_code_expected > 0 else 0

    return BenchmarkResult(
        config=cfg,
        file_accuracy=file_accuracy,
        file_mrr=file_mrr,
        chunk_keyword_recall=chunk_recall,
        graph_code_recall=graph_recall,
        index_time_s=index_time,
        first_query_ms=query_times[0] if query_times else 0,
        avg_query_ms=sum(query_times) / len(query_times) if query_times else 0,
        query_results=query_results,
    )


def main():
    """Run comprehensive benchmark."""
    # Source directories - verified paths
    charmarr_meta = Path.home() / "Repo/charmarr/charmarr-meta/adr"
    charmarr_lib_core = Path.home() / "Repo/charmarr/charmarr-lib/core/src"
    charmarr_lib_vpn = Path.home() / "Repo/charmarr/charmarr-lib/vpn/src"

    source_dirs = []
    if charmarr_meta.exists():
        source_dirs.append((charmarr_meta, "adr"))
        print(f"+ ADRs: {charmarr_meta}")
    if charmarr_lib_core.exists():
        source_dirs.append((charmarr_lib_core, "code"))
        print(f"+ Core lib: {charmarr_lib_core}")
    if charmarr_lib_vpn.exists():
        source_dirs.append((charmarr_lib_vpn, "code"))
        print(f"+ VPN lib: {charmarr_lib_vpn}")

    if len(source_dirs) < 2:
        print("ERROR: Need both ADRs and code directories!")
        return

    # Count files
    total_files = 0
    for src_dir, src_type in source_dirs:
        if src_type == "adr":
            total_files += len(list(src_dir.rglob("*.md")))
        else:
            total_files += len([f for f in src_dir.rglob("*.py")
                               if "test_" not in f.name and "__" not in f.name])

    print(f"\nTotal files: {total_files}")
    print(f"Total queries: {len(QUERIES)}")
    print(f"Configurations: {len(CONFIGS)}")

    print("\n" + "=" * 100)
    print("COMPREHENSIVE GUNDOG BENCHMARK")
    print("=" * 100)

    results = []

    for i, cfg in enumerate(CONFIGS, 1):
        print(f"\n[{i}/{len(CONFIGS)}] {cfg.name}")
        print(f"    model={cfg.model.split('/')[-1]}, storage={cfg.storage_backend}, embedder={cfg.embedding_backend}")

        result = run_benchmark(cfg, source_dirs)
        results.append(result)

        print(f"    File Accuracy: {result.file_accuracy:.1%}")
        print(f"    File MRR: {result.file_mrr:.3f}")
        print(f"    Chunk Keyword Recall: {result.chunk_keyword_recall:.1%}")
        print(f"    Graph Code Recall: {result.graph_code_recall:.1%}")
        print(f"    Index: {result.index_time_s:.1f}s, 1st Query: {result.first_query_ms:.0f}ms, Avg: {result.avg_query_ms:.1f}ms")

    # Summary table
    print("\n" + "=" * 100)
    print("SUMMARY TABLE")
    print("=" * 100)
    print(f"{'Config':<20} {'FileAcc':<8} {'MRR':<6} {'ChunkR':<8} {'GraphR':<8} {'1stQ':<8} {'AvgQ':<8} {'Index':<8}")
    print("-" * 84)

    for r in results:
        print(f"{r.config.name:<20} {r.file_accuracy:<8.1%} {r.file_mrr:<6.3f} {r.chunk_keyword_recall:<8.1%} {r.graph_code_recall:<8.1%} {r.first_query_ms:<8.0f} {r.avg_query_ms:<8.1f} {r.index_time_s:<8.1f}")

    # Category breakdown for best config
    print("\n" + "=" * 100)
    print("CATEGORY BREAKDOWN (best config: base_hnsw_onnx)")
    print("=" * 100)

    best = next((r for r in results if r.config.name == "base_hnsw_onnx"), results[-1])
    categories = {}
    for qr in best.query_results:
        if qr.category not in categories:
            categories[qr.category] = {"found": 0, "total": 0, "code_found": 0, "code_total": 0}
        categories[qr.category]["total"] += 1
        categories[qr.category]["code_total"] += qr.code_files_expected
        if qr.file_found:
            categories[qr.category]["found"] += 1
        categories[qr.category]["code_found"] += qr.code_files_found

    print(f"{'Category':<12} {'File Acc':<10} {'Graph Code Recall':<20}")
    print("-" * 42)
    for cat, data in sorted(categories.items()):
        file_acc = data["found"] / data["total"] if data["total"] > 0 else 0
        code_recall = data["code_found"] / data["code_total"] if data["code_total"] > 0 else 0
        print(f"{cat:<12} {file_acc:<10.0%} {code_recall:<20.0%}")

    # Save results
    output = {
        "metadata": {
            "total_files": total_files,
            "total_queries": len(QUERIES),
            "source_dirs": [str(s[0]) for s in source_dirs],
        },
        "results": [
            {
                "config": {
                    "name": r.config.name,
                    "model": r.config.model,
                    "storage": r.config.storage_backend,
                    "embedder": r.config.embedding_backend,
                },
                "file_accuracy": r.file_accuracy,
                "file_mrr": r.file_mrr,
                "chunk_keyword_recall": r.chunk_keyword_recall,
                "graph_code_recall": r.graph_code_recall,
                "index_time_s": r.index_time_s,
                "first_query_ms": r.first_query_ms,
                "avg_query_ms": r.avg_query_ms,
            }
            for r in results
        ],
    }

    output_path = Path(__file__).parent / "benchmark_results_comprehensive.json"
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\nResults saved to: {output_path}")


if __name__ == "__main__":
    main()
