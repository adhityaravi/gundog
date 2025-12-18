#!/usr/bin/env python3
"""
Mixed Benchmark - 3 codebases combined without categories

Dataset:
- charmarr (ADRs + Python)
- kubeloom (Python)
- service-mesh/docs (Markdown)

Tests how well models handle mixed domain data.
"""

import json
import shutil
import sys
import time
from dataclasses import dataclass, field
from io import StringIO
from pathlib import Path

# Mixed queries - covering all 3 codebases with correct expected files
QUERIES = [
    # Charmarr queries (10)
    {"q": "how do arr apps share api keys between each other", "expected": "adr-002-cross-app-auth"},
    {"q": "qbittorrent password storage and hashing mechanism", "expected": "adr-002-cross-app-auth"},
    {"q": "how does the vpn killswitch prevent leaks", "expected": "adr-004-vpn-kill-switch"},
    {"q": "gluetun container network firewall rules", "expected": "adr-004-vpn-kill-switch"},
    {"q": "pvc patching for statefulset volumes kubernetes", "expected": "adr-003-pvc-patching"},
    {"q": "prowlarr app registration and sync level config", "expected": "adr-008-prowlarr"},
    {"q": "download client qbit vs sabnzbd auth differences", "expected": "adr-004-download-client"},
    {"q": "aggressive vs gentle reconciliation strategy", "expected": "adr-003-reconciliation"},
    {"q": "network policy egress cluster cidr whitelist", "expected": "_kill_switch"},
    {"q": "base arr api client http request handling", "expected": "_base_client"},
    # Kubeloom queries (8)
    {"q": "kubernetes service mesh policy analyzer", "expected": "policy_analyzer"},
    {"q": "istio log parsing and network flow analysis", "expected": "log_parser"},
    {"q": "cluster model validation and errors", "expected": "validation"},
    {"q": "kubeloom cli commands and main entry point", "expected": "commands"},
    {"q": "network action models for kubernetes", "expected": "actions"},
    {"q": "source models for cluster resources", "expected": "sources"},
    {"q": "core interfaces and abstract base classes", "expected": "interfaces"},
    {"q": "mesh analysis and service discovery", "expected": "mesh"},
    # Service-mesh docs queries (8) - FIXED to match actual filenames
    {"q": "istio service mesh getting started tutorial", "expected": "get-started"},
    {"q": "what is istio and how does it work", "expected": "istio.md"},
    {"q": "service mesh concepts and architecture", "expected": "service-mesh.md"},
    {"q": "traffic authorization policies", "expected": "traffic-authorization"},
    {"q": "hardened security mode configuration", "expected": "hardened-mode"},
    {"q": "managed mode vs hardened mode", "expected": "managed-mode"},
    {"q": "kiali monitoring dashboard tutorial", "expected": "kiali"},
    {"q": "add mesh support to your charm howto", "expected": "add-mesh-support"},
]


@dataclass
class Config:
    name: str
    model: str
    storage_backend: str
    embedding_backend: str


@dataclass
class BenchmarkResult:
    config: Config
    file_accuracy: float
    file_mrr: float
    index_time_s: float
    first_query_ms: float
    avg_query_ms: float
    total_files: int
    total_chunks: int
    failed_queries: list[str] = field(default_factory=list)


CONFIGS = [
    # Baseline: numpy + sentence-transformers
    Config("small_numpy_st", "BAAI/bge-small-en-v1.5", "numpy", "sentence-transformers"),
    # HNSW variants
    Config("small_hnsw_st", "BAAI/bge-small-en-v1.5", "hnsw", "sentence-transformers"),
    Config("small_hnsw_onnx", "BAAI/bge-small-en-v1.5", "hnsw", "onnx"),
    # Base model
    Config("base_hnsw_onnx", "BAAI/bge-base-en-v1.5", "hnsw", "onnx"),
    # LanceDB - DISABLED: takes 18+ minutes for 152 files (17x slower than numpy)
    # Config("small_lance_st", "BAAI/bge-small-en-v1.5", "lancedb", "sentence-transformers"),
]


def run_benchmark(cfg: Config, source_dirs: list[tuple[Path, str]]) -> BenchmarkResult:
    """Run benchmark for a configuration."""
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

    index_path = f"/tmp/gundog_mixed_{cfg.name}"

    # Build sources
    sources = []
    for src_dir, src_type in source_dirs:
        if src_type == "docs":
            sources.append(SourceConfig(
                path=str(src_dir),
                glob="**/*.md",
                type="doc",
                ignore=["**/README.md", "**/_build/**", "**/.sphinx/**", "**/venv/**"],
            ))
        elif src_type == "adr":
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

    gundog_cfg = GundogConfig(
        sources=sources,
        embedding=EmbeddingConfig(model=cfg.model, backend=cfg.embedding_backend),
        storage=StorageConfig(backend=cfg.storage_backend, path=index_path),
        hybrid=HybridConfig(enabled=True),
        chunking=ChunkingConfig(enabled=True, max_tokens=512, overlap_tokens=50),
        graph=GraphConfig(similarity_threshold=0.65, max_expand_depth=2),
    )

    # Count files
    total_files = 0
    for src_dir, src_type in source_dirs:
        if src_type in ("docs", "adr"):
            total_files += len([f for f in src_dir.rglob("*.md")
                               if "_build" not in str(f) and ".sphinx" not in str(f) and "venv" not in str(f)])
        else:
            total_files += len([f for f in src_dir.rglob("*.py")
                               if "test_" not in f.name and "__" not in f.name])

    # Clean and index
    idx_path = Path(index_path)
    if idx_path.exists():
        shutil.rmtree(idx_path)
    idx_path.mkdir(parents=True)

    old_stdout = sys.stdout
    sys.stdout = StringIO()

    index_start = time.perf_counter()
    indexer = Indexer(gundog_cfg)
    summary = indexer.index(rebuild=True)
    index_time = time.perf_counter() - index_start

    sys.stdout = old_stdout

    total_chunks = summary.total_chunks if hasattr(summary, 'total_chunks') else 0

    # Query
    engine = QueryEngine(gundog_cfg)
    query_times = []
    found_count = 0
    mrr_sum = 0
    failed = []

    for q_data in QUERIES:
        query = q_data["q"]
        expected = q_data["expected"]

        start = time.perf_counter()
        result = engine.query(query, top_k=10, expand=False, min_score=0.25)
        elapsed_ms = (time.perf_counter() - start) * 1000
        query_times.append(elapsed_ms)

        file_found = False
        file_rank = -1
        for j, r in enumerate(result.direct[:10]):
            if expected.lower() in r["path"].lower():
                file_found = True
                file_rank = j + 1
                break

        if file_found:
            found_count += 1
            mrr_sum += 1 / file_rank
        else:
            failed.append(f"{query[:40]}... (expected: {expected})")

    file_accuracy = found_count / len(QUERIES)
    file_mrr = mrr_sum / len(QUERIES)

    return BenchmarkResult(
        config=cfg,
        file_accuracy=file_accuracy,
        file_mrr=file_mrr,
        index_time_s=index_time,
        first_query_ms=query_times[0] if query_times else 0,
        avg_query_ms=sum(query_times) / len(query_times) if query_times else 0,
        total_files=total_files,
        total_chunks=total_chunks,
        failed_queries=failed,
    )


def main():
    """Run mixed benchmark."""
    sources = []

    # Charmarr
    charmarr_meta = Path.home() / "Repo/charmarr/charmarr-meta/adr"
    charmarr_lib_core = Path.home() / "Repo/charmarr/charmarr-lib/core/src"
    charmarr_lib_vpn = Path.home() / "Repo/charmarr/charmarr-lib/vpn/src"

    if charmarr_meta.exists():
        sources.append((charmarr_meta, "adr"))
    if charmarr_lib_core.exists():
        sources.append((charmarr_lib_core, "code"))
    if charmarr_lib_vpn.exists():
        sources.append((charmarr_lib_vpn, "code"))

    # Kubeloom
    kubeloom_src = Path.home() / "Repo/kubeloom/src"
    if kubeloom_src.exists():
        sources.append((kubeloom_src, "code"))

    # Service-mesh docs
    servicemesh_docs = Path.home() / "Work/repo/service-mesh/docs"
    if servicemesh_docs.exists():
        sources.append((servicemesh_docs, "docs"))

    print("=" * 80)
    print("MIXED BENCHMARK - 3 Codebases Combined")
    print("=" * 80)
    print(f"Sources: {len(sources)}")
    for s, t in sources:
        print(f"  [{t}] {s}")
    print(f"Queries: {len(QUERIES)}")

    results = []
    for i, cfg in enumerate(CONFIGS, 1):
        print(f"\n[{i}/{len(CONFIGS)}] {cfg.name}")
        print(f"    model={cfg.model.split('/')[-1]}, storage={cfg.storage_backend}, embedder={cfg.embedding_backend}")

        result = run_benchmark(cfg, sources)
        results.append(result)

        print(f"    Files: {result.total_files}, Chunks: {result.total_chunks}")
        print(f"    File Accuracy: {result.file_accuracy:.1%}")
        print(f"    MRR: {result.file_mrr:.3f}")
        print(f"    Index: {result.index_time_s:.1f}s")
        print(f"    1st Query: {result.first_query_ms:.0f}ms")
        print(f"    Avg Query: {result.avg_query_ms:.1f}ms")

        if result.failed_queries:
            print(f"    Failed ({len(result.failed_queries)}):")
            for f in result.failed_queries[:5]:
                print(f"      - {f}")

    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"{'Config':<20} {'Files':<8} {'Chunks':<8} {'Accuracy':<10} {'MRR':<8} {'1stQ':<10} {'AvgQ':<10} {'Index':<8}")
    print("-" * 82)
    for r in results:
        print(f"{r.config.name:<20} {r.total_files:<8} {r.total_chunks:<8} {r.file_accuracy:<10.1%} {r.file_mrr:<8.3f} {r.first_query_ms:<10.0f} {r.avg_query_ms:<10.1f} {r.index_time_s:<8.1f}")

    # Save
    output = {
        "metadata": {
            "sources": [str(s[0]) for s in sources],
            "total_queries": len(QUERIES),
        },
        "results": [{
            "config": r.config.name,
            "total_files": r.total_files,
            "total_chunks": r.total_chunks,
            "file_accuracy": r.file_accuracy,
            "file_mrr": r.file_mrr,
            "index_time_s": r.index_time_s,
            "first_query_ms": r.first_query_ms,
            "avg_query_ms": r.avg_query_ms,
            "failed_queries": r.failed_queries,
        } for r in results]
    }
    with open("benchmark_results_mixed.json", "w") as f:
        json.dump(output, f, indent=2)
    print(f"\nResults saved to: benchmark_results_mixed.json")


if __name__ == "__main__":
    main()
