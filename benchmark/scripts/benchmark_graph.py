#!/usr/bin/env python3
"""Benchmark graph expansion quality.

Tests whether graph expansion finds semantically related documents
beyond direct query matches.
"""

import json
import sys
import tempfile
import time
from dataclasses import dataclass
from io import StringIO
from pathlib import Path

# Test cases for graph expansion
GRAPH_TEST_CASES = [
    {
        "query": "How is download client authentication implemented?",
        "expected_direct": ["download-client", "auth"],
        "expected_related": ["reconciler", "api", "client"],
        "description": "Auth ADR should connect to implementation",
    },
    {
        "query": "VPN kill switch network policy",
        "expected_direct": ["kill-switch", "vpn"],
        "expected_related": ["network", "egress", "policy"],
        "description": "VPN ADR should connect to k8s implementation",
    },
    {
        "query": "Prowlarr indexer synchronization",
        "expected_direct": ["prowlarr", "indexer"],
        "expected_related": ["sync", "application", "api"],
        "description": "Prowlarr ADR should link to API client",
    },
    {
        "query": "PVC storage patching StatefulSet",
        "expected_direct": ["pvc", "storage"],
        "expected_related": ["patch", "stateful", "volume"],
        "description": "Storage ADR should link to k8s code",
    },
    {
        "query": "credentials secret management rotation",
        "expected_direct": ["secret", "credential"],
        "expected_related": ["juju", "api", "key"],
        "description": "Secrets ADR should link to implementations",
    },
]


@dataclass
class GraphTestResult:
    query: str
    description: str
    direct_found: list[str]
    related_found: list[str]
    expected_related: list[str]
    related_recall: float
    expansion_count: int
    graph_edges: int
    query_time_ms: float


def run_graph_benchmark(
    source_dirs: list[tuple[Path, str]],
    similarity_threshold: float = 0.60,
) -> tuple[list[GraphTestResult], dict]:
    """Run graph expansion benchmark.

    Returns results and graph stats.
    """
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

    results = []

    with tempfile.TemporaryDirectory() as tmpdir:
        index_path = Path(tmpdir) / "index"

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
                    ignore=["**/__pycache__/**", "**/.venv/**", "**/__init__.py"],
                ))

        # Build config
        config = GundogConfig(
            sources=sources,
            embedding=EmbeddingConfig(model="BAAI/bge-small-en-v1.5", backend="onnx"),
            storage=StorageConfig(backend="hnsw", path=str(index_path)),
            hybrid=HybridConfig(enabled=True),
            chunking=ChunkingConfig(enabled=True, max_tokens=512, overlap_tokens=50),
            graph=GraphConfig(
                similarity_threshold=similarity_threshold,
                max_expand_depth=2,
                expand_threshold=0.55,
            ),
        )

        # Suppress output during indexing
        old_stdout = sys.stdout
        sys.stdout = StringIO()

        indexer = Indexer(config)
        indexer.index(rebuild=True)

        sys.stdout = old_stdout

        # Load graph stats
        graph_path = Path(config.storage.path) / "graph.json"
        graph_data = json.loads(graph_path.read_text()) if graph_path.exists() else {}
        edge_count = len(graph_data.get("edges", []))
        node_count = len(graph_data.get("nodes", {}))

        # Query engine
        engine = QueryEngine(config)

        # Run test cases
        for test_case in GRAPH_TEST_CASES:
            query = test_case["query"]
            expected_related = test_case["expected_related"]

            start = time.perf_counter()
            result = engine.query(
                query_text=query,
                top_k=5,
                expand=True,
                expand_depth=2,
            )
            query_time = (time.perf_counter() - start) * 1000

            # Check what we found
            direct_files = [Path(r["path"]).name for r in result.direct]
            related_files = [Path(r["path"]).name for r in result.related]

            # Calculate recall for expected related keywords
            all_found = set(f.lower() for f in direct_files + related_files)
            all_text = " ".join(all_found)
            related_matches = sum(
                1 for exp in expected_related
                if exp.lower() in all_text
            )
            related_recall = related_matches / len(expected_related) if expected_related else 0

            results.append(GraphTestResult(
                query=query,
                description=test_case["description"],
                direct_found=direct_files[:5],
                related_found=related_files[:10],
                expected_related=expected_related,
                related_recall=related_recall,
                expansion_count=len(result.related),
                graph_edges=edge_count,
                query_time_ms=query_time,
            ))

        graph_stats = {
            "edges": edge_count,
            "nodes": node_count,
            "top_edges": sorted(
                graph_data.get("edges", []),
                key=lambda e: e["weight"],
                reverse=True
            )[:20] if graph_data else [],
        }

    return results, graph_stats


def main():
    """Run graph expansion benchmark."""
    # Source directories
    charmarr_meta = Path.home() / "Repo/charmarr/charmarr-meta/adr"
    charmarr_lib_core = Path.home() / "Repo/charmarr/charmarr-lib/core/src"
    charmarr_lib_vpn = Path.home() / "Repo/charmarr/charmarr-lib/vpn/src"

    source_dirs = []
    if charmarr_meta.exists():
        source_dirs.append((charmarr_meta, "adr"))
    if charmarr_lib_core.exists():
        source_dirs.append((charmarr_lib_core, "code"))
    if charmarr_lib_vpn.exists():
        source_dirs.append((charmarr_lib_vpn, "code"))

    if not source_dirs:
        print("No source directories found!")
        return

    print("=" * 80)
    print("GRAPH EXPANSION BENCHMARK")
    print("=" * 80)
    print(f"Sources: {[str(s[0]) for s in source_dirs]}")

    # Test with different similarity thresholds
    thresholds = [0.50, 0.55, 0.60, 0.65, 0.70]
    all_results = {}

    for threshold in thresholds:
        print(f"\n{'='*60}")
        print(f"Similarity Threshold: {threshold}")
        print("=" * 60)

        results, graph_stats = run_graph_benchmark(source_dirs, threshold)
        all_results[threshold] = {"results": results, "graph_stats": graph_stats}

        total_recall = sum(r.related_recall for r in results) / len(results)
        total_expanded = sum(r.expansion_count for r in results)
        avg_query_time = sum(r.query_time_ms for r in results) / len(results)

        print(f"Graph: {graph_stats['nodes']} nodes, {graph_stats['edges']} edges")
        print(f"Avg related keyword recall: {total_recall:.1%}")
        print(f"Total expansions found: {total_expanded}")
        print(f"Avg query time: {avg_query_time:.1f}ms")

        print("\nPer-query results:")
        for r in results:
            status = "+" if r.related_recall > 0.5 else "-"
            print(f"  [{status}] {r.query[:45]}...")
            print(f"      Direct: {r.direct_found[:3]}")
            print(f"      Related ({r.expansion_count}): {r.related_found[:5]}")
            print(f"      Recall: {r.related_recall:.0%} ({r.expected_related})")

    # Summary comparison
    print("\n" + "=" * 80)
    print("THRESHOLD COMPARISON SUMMARY")
    print("=" * 80)
    print(f"{'Threshold':<12} {'Edges':<8} {'Expansions':<12} {'Recall':<10} {'Query ms':<10}")
    print("-" * 52)

    for threshold, data in all_results.items():
        results = data["results"]
        edges = data["graph_stats"]["edges"]
        expansions = sum(r.expansion_count for r in results)
        recall = sum(r.related_recall for r in results) / len(results)
        query_ms = sum(r.query_time_ms for r in results) / len(results)
        print(f"{threshold:<12} {edges:<8} {expansions:<12} {recall:<10.1%} {query_ms:<10.1f}")

    # Show top graph edges at best threshold
    best_threshold = 0.60
    print(f"\n{'='*80}")
    print(f"TOP GRAPH EDGES (threshold={best_threshold})")
    print("=" * 80)

    top_edges = all_results[best_threshold]["graph_stats"]["top_edges"]
    for e in top_edges[:15]:
        src = Path(e["source"]).name
        tgt = Path(e["target"]).name
        weight = e["weight"]
        # Truncate long names
        src = src[:25] + "..." if len(src) > 28 else src
        tgt = tgt[:25] + "..." if len(tgt) > 28 else tgt
        print(f"  {src:<28} <-> {tgt:<28} ({weight:.3f})")


if __name__ == "__main__":
    main()
