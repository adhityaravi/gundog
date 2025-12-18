#!/usr/bin/env python3
"""
Full benchmark comparing:
- Models: bge-small-en-v1.5, bge-base-en-v1.5
- Storage: numpy, lancedb, hnsw
- Embedder: sentence-transformers, onnx
- Chunking: enabled with BM25 + TF-IDF

Dataset: 60 files (44 ADRs + 16 Python), 50 queries
"""

import json
import shutil
import sys
import time
from dataclasses import dataclass
from io import StringIO
from pathlib import Path

# Source directories
ADR_DIR = Path.home() / "Repo/charmarr/charmarr-meta/adr"
LIB_DIR = Path.home() / "Repo/charmarr/charmarr-lib"

# 50 queries (same as before)
QUERIES = [
    # Authentication & Credentials (5)
    {"q": "How are API keys managed for arr apps?", "expected": "adr-002-cross-app-auth"},
    {"q": "qBittorrent password hashing PBKDF2 SHA512", "expected": "adr-002-cross-app-auth"},
    {"q": "credential drift detection update-status hook", "expected": "adr-002-cross-app-auth"},
    {"q": "Juju secrets API key rotation", "expected": "adr-002-secret-management"},
    {"q": "secret-changed event propagation to observers", "expected": "adr-002-secret-management"},
    # Storage & PVC (6)
    {"q": "workload-less Kubernetes charm architecture lightkube", "expected": "adr-005-charmarr-storage"},
    {"q": "PVC access mode ReadWriteMany ReadWriteOnce StorageClass", "expected": "adr-005-charmarr-storage"},
    {"q": "PUID PGID file ownership LinuxServer containers", "expected": "adr-005-charmarr-storage"},
    {"q": "hardlinks media storage same filesystem Trash Guides", "expected": "adr-001-shared-pvc"},
    {"q": "multi-node NFS vs local storage deployment", "expected": "adr-001-shared-pvc"},
    {"q": "StatefulSet PVC patching volume mount", "expected": "adr-003-pvc-patching"},
    # Reconciliation (4)
    {"q": "aggressive vs respectful reconciliation strategy", "expected": "adr-003-reconciliation"},
    {"q": "infrastructure configuration managed by Juju delete override", "expected": "adr-003-reconciliation"},
    {"q": "user preferences quality profiles preserved", "expected": "adr-003-reconciliation"},
    {"q": "self-healing credential sync pattern", "expected": "adr-003-reconciliation"},
    # Download Client (4)
    {"q": "download client qBittorrent SABnzbd authentication method", "expected": "adr-004-download-client"},
    {"q": "torrent usenet client type semantic distinction", "expected": "adr-004-download-client"},
    {"q": "DownloadClientProviderData pydantic model", "expected": "adr-004-download-client"},
    {"q": "credentials_secret_id vs api_key_secret_id", "expected": "adr-004-download-client"},
    # VPN & Networking (8)
    {"q": "VPN kill switch NetworkPolicy implementation", "expected": "adr-004-vpn-kill-switch"},
    {"q": "gluetun firewall two-layer defense", "expected": "adr-004-vpn-kill-switch"},
    {"q": "VXLAN encapsulation gateway pod routing", "expected": "adr-004-vpn-kill-switch"},
    {"q": "cluster CIDR egress allow rule", "expected": "adr-004-vpn-kill-switch"},
    {"q": "VPN gateway interface provider requirer", "expected": "adr-007-vpn-gateway"},
    {"q": "download client egress traffic routing", "expected": "adr-003-download-client-egress"},
    {"q": "Istio service mesh VPN integration", "expected": "adr-005-istio"},
    {"q": "ingress controller traefik configuration", "expected": "adr-001-ingress"},
    # Prowlarr & Media Indexer (5)
    {"q": "Prowlarr application registration syncLevel fullSync", "expected": "adr-008-prowlarr"},
    {"q": "ProwlarrApiClient vs ArrApiClient base class", "expected": "adr-008-prowlarr"},
    {"q": "media-indexer interface indexer synchronization", "expected": "adr-003-media-indexer"},
    {"q": "indexer tags filtering radarr sonarr", "expected": "adr-008-prowlarr"},
    {"q": "MediaIndexerRequirerData provider data model", "expected": "adr-003-media-indexer"},
    # Media Manager & Apps (5)
    {"q": "Radarr Sonarr charm implementation v3 API", "expected": "adr-004-radarr-sonarr"},
    {"q": "quality profile default selection Overseerr", "expected": "adr-006-media-manager"},
    {"q": "Plex media server library scanning", "expected": "adr-009-plex"},
    {"q": "Recyclarr custom format sync Trash Guides", "expected": "adr-003-recyclarr"},
    {"q": "app scaling horizontal v2 multiple instances", "expected": "adr-013-app-scaling"},
    # Python - Reconcilers (5)
    {"q": "reconcile_download_clients function delete sync", "expected": "_reconcilers.py"},
    {"q": "_needs_download_client_update field comparison", "expected": "_reconcilers.py"},
    {"q": "reconcile_prowlarr_applications registration", "expected": "_reconcilers.py"},
    {"q": "DownloadClientConfigBuilder category field", "expected": "_config_builders.py"},
    {"q": "ApplicationConfigBuilder prowlarr sync", "expected": "_config_builders.py"},
    # Python - API Clients (4)
    {"q": "ArrApiClient get_download_clients method", "expected": "_arr_client.py"},
    {"q": "BaseArrApiClient HTTP request retry", "expected": "_base_client.py"},
    {"q": "ProwlarrApiClient get_applications endpoint", "expected": "_prowlarr_client.py"},
    {"q": "api_url api_key authentication header", "expected": "_base_client.py"},
    # Python - K8s & Storage (4)
    {"q": "KillSwitchConfig pydantic cluster_cidrs", "expected": "_kill_switch.py"},
    {"q": "_build_kill_switch_policy NetworkPolicy egress", "expected": "_kill_switch.py"},
    {"q": "MediaStorageProviderData pvc_name mount_path", "expected": "_media_storage.py"},
    {"q": "patch_statefulset_volume lightkube", "expected": "_storage.py"},
]


@dataclass
class Config:
    """Benchmark configuration."""
    name: str
    model: str
    storage_backend: str
    embedding_backend: str  # sentence-transformers or onnx


# Configurations to test
CONFIGS = [
    # Baseline: small model, different storage backends
    Config("small_numpy_st", "BAAI/bge-small-en-v1.5", "numpy", "sentence-transformers"),
    Config("small_lance_st", "BAAI/bge-small-en-v1.5", "lancedb", "sentence-transformers"),
    Config("small_hnsw_st", "BAAI/bge-small-en-v1.5", "hnsw", "sentence-transformers"),

    # Small model with ONNX
    Config("small_hnsw_onnx", "BAAI/bge-small-en-v1.5", "hnsw", "onnx"),

    # Base model (larger, better accuracy?)
    Config("base_numpy_st", "BAAI/bge-base-en-v1.5", "numpy", "sentence-transformers"),
    Config("base_hnsw_st", "BAAI/bge-base-en-v1.5", "hnsw", "sentence-transformers"),
    Config("base_hnsw_onnx", "BAAI/bge-base-en-v1.5", "hnsw", "onnx"),
]


def run_benchmark(cfg: Config, source_dirs: list[tuple[Path, str]]) -> dict:
    """Run indexing and queries for one configuration."""
    from gundog._config import (
        GundogConfig, SourceConfig, EmbeddingConfig,
        StorageConfig, HybridConfig, ChunkingConfig, GraphConfig,
    )
    from gundog._indexer import Indexer
    from gundog._query import QueryEngine

    index_path = f"/tmp/gundog_full_{cfg.name}"

    # Build sources config
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
                ignore=["**/__pycache__/**", "**/.venv/**", "**/__init__.py", "**/_version.py"],
            ))

    # Build config
    gundog_cfg = GundogConfig(
        sources=sources,
        embedding=EmbeddingConfig(
            model=cfg.model,
            backend=cfg.embedding_backend,
        ),
        storage=StorageConfig(backend=cfg.storage_backend, path=index_path),
        hybrid=HybridConfig(enabled=True),
        chunking=ChunkingConfig(enabled=True, max_tokens=512, overlap_tokens=50),
        graph=GraphConfig(similarity_threshold=0.65),
    )

    # Clean index
    idx_path = Path(index_path)
    if idx_path.exists():
        shutil.rmtree(idx_path)
    idx_path.mkdir(parents=True)

    # Suppress indexing output
    old_stdout = sys.stdout
    sys.stdout = StringIO()

    # Index
    index_start = time.perf_counter()
    indexer = Indexer(gundog_cfg)
    summary = indexer.index(rebuild=True)
    index_time = time.perf_counter() - index_start

    sys.stdout = old_stdout

    # Query
    engine = QueryEngine(gundog_cfg)

    query_results = []
    query_times = []

    for q_data in QUERIES:
        query = q_data["q"]
        expected = q_data["expected"]

        start = time.perf_counter()
        result = engine.query(query, top_k=10, expand=False, min_score=0.25)
        elapsed_ms = (time.perf_counter() - start) * 1000
        query_times.append(elapsed_ms)

        # Check accuracy
        hit = False
        rank = -1
        for i, r in enumerate(result.direct[:10]):
            if expected in r["path"]:
                hit = True
                rank = i + 1
                break

        query_results.append({
            "query": query,
            "expected": expected,
            "hit": hit,
            "rank": rank,
            "time_ms": round(elapsed_ms, 2),
        })

    # Metrics
    hits = sum(1 for r in query_results if r["hit"])
    rank1 = sum(1 for r in query_results if r["rank"] == 1)
    top3 = sum(1 for r in query_results if r["hit"] and r["rank"] <= 3)
    avg_rank = sum(r["rank"] for r in query_results if r["hit"]) / max(hits, 1)

    # Query time stats (exclude first query - model loading)
    avg_query = sum(query_times[1:]) / len(query_times[1:]) if len(query_times) > 1 else query_times[0]
    first_query = query_times[0]

    return {
        "config": cfg.name,
        "model": cfg.model.split("/")[-1],
        "storage": cfg.storage_backend,
        "embedder": cfg.embedding_backend,
        "files": summary.get("files_indexed", summary.get("files_total")),
        "chunks": summary.get("chunks_indexed", "N/A"),
        "index_time_s": round(index_time, 2),
        "accuracy": round(hits / len(QUERIES), 4),
        "hits": hits,
        "rank1": rank1,
        "top3": top3,
        "avg_rank": round(avg_rank, 2),
        "first_query_ms": round(first_query, 1),
        "avg_query_ms": round(avg_query, 2),
        "query_results": query_results,
    }


def main():
    print("=" * 80)
    print("GUNDOG FULL BENCHMARK: Models × Storage × Embedder")
    print("=" * 80)

    source_dirs = [
        (ADR_DIR, "adr"),
        (LIB_DIR / "core/src", "code"),
        (LIB_DIR / "vpn/src", "code"),
        (LIB_DIR / "testing/src", "code"),
        (LIB_DIR / "krm/src", "code"),
    ]

    print(f"Queries: {len(QUERIES)}")
    print(f"Configurations: {len(CONFIGS)}")
    print()

    all_results = []

    for i, cfg in enumerate(CONFIGS):
        print(f"[{i+1}/{len(CONFIGS)}] {cfg.name}")
        print(f"    model={cfg.model.split('/')[-1]}, storage={cfg.storage_backend}, embedder={cfg.embedding_backend}")

        result = run_benchmark(cfg, source_dirs)
        all_results.append(result)

        print(f"    → Acc: {result['accuracy']*100:.1f}% ({result['hits']}/50), "
              f"R1: {result['rank1']}, Top3: {result['top3']}, AvgRank: {result['avg_rank']:.2f}")
        print(f"    → Index: {result['index_time_s']:.1f}s, "
              f"1st Query: {result['first_query_ms']:.0f}ms, Avg Query: {result['avg_query_ms']:.1f}ms")
        print()

    # Summary table
    print("=" * 80)
    print("SUMMARY TABLE")
    print("=" * 80)
    print()

    header = f"{'Config':<20} {'Model':<12} {'Store':<8} {'Embed':<6} {'Acc':>6} {'R1':>4} {'Top3':>5} {'AvgR':>5} {'1stQ':>7} {'AvgQ':>7} {'Idx':>6}"
    print(header)
    print("-" * len(header))

    for r in all_results:
        model_short = "small" if "small" in r["model"] else "base"
        embed_short = "ST" if r["embedder"] == "sentence-transformers" else "ONNX"
        print(f"{r['config']:<20} {model_short:<12} {r['storage']:<8} {embed_short:<6} "
              f"{r['accuracy']*100:>5.1f}% {r['rank1']:>4} {r['top3']:>5} {r['avg_rank']:>5.2f} "
              f"{r['first_query_ms']:>6.0f}ms {r['avg_query_ms']:>6.1f}ms {r['index_time_s']:>5.1f}s")

    # Save results
    output_path = Path("/home/ivdi/Repo/gundog/benchmark_results_full.json")

    summary = {
        "configs": [r["config"] for r in all_results],
        "accuracy_pct": [r["accuracy"] * 100 for r in all_results],
        "rank1": [r["rank1"] for r in all_results],
        "top3": [r["top3"] for r in all_results],
        "avg_rank": [r["avg_rank"] for r in all_results],
        "first_query_ms": [r["first_query_ms"] for r in all_results],
        "avg_query_ms": [r["avg_query_ms"] for r in all_results],
        "index_time_s": [r["index_time_s"] for r in all_results],
    }

    with open(output_path, "w") as f:
        json.dump({
            "metadata": {
                "queries": len(QUERIES),
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            },
            "summary": summary,
            "results": all_results,
        }, f, indent=2)

    print()
    print(f"Results saved to: {output_path}")

    # Key comparisons
    print()
    print("=" * 80)
    print("KEY COMPARISONS")
    print("=" * 80)

    # Find results by name
    def get_result(name):
        return next((r for r in all_results if r["config"] == name), None)

    # Storage comparison (small model, ST)
    print("\n1. STORAGE BACKEND (small model, sentence-transformers):")
    for name in ["small_numpy_st", "small_lance_st", "small_hnsw_st"]:
        r = get_result(name)
        if r:
            print(f"   {r['storage']:<8}: Acc={r['accuracy']*100:.1f}%, AvgQuery={r['avg_query_ms']:.1f}ms")

    # Embedder comparison (small model, hnsw)
    print("\n2. EMBEDDER BACKEND (small model, hnsw):")
    for name in ["small_hnsw_st", "small_hnsw_onnx"]:
        r = get_result(name)
        if r:
            embed = "ST" if "st" in name else "ONNX"
            print(f"   {embed:<8}: 1stQuery={r['first_query_ms']:.0f}ms, AvgQuery={r['avg_query_ms']:.1f}ms")

    # Model comparison (hnsw, ST)
    print("\n3. MODEL SIZE (hnsw, sentence-transformers):")
    for name in ["small_hnsw_st", "base_hnsw_st"]:
        r = get_result(name)
        if r:
            model = "small" if "small" in name else "base"
            print(f"   {model:<8}: Acc={r['accuracy']*100:.1f}%, R1={r['rank1']}, AvgRank={r['avg_rank']:.2f}")

    # Best overall
    print("\n4. BEST CONFIGS:")
    best_acc = max(all_results, key=lambda r: r["accuracy"])
    best_speed = min(all_results, key=lambda r: r["avg_query_ms"])
    print(f"   Best accuracy: {best_acc['config']} ({best_acc['accuracy']*100:.1f}%)")
    print(f"   Best speed:    {best_speed['config']} ({best_speed['avg_query_ms']:.1f}ms avg)")


if __name__ == "__main__":
    main()
