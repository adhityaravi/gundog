"""Graph visualization generation."""

import json
import re
from pathlib import Path

from gundog._graph import SimilarityGraph


def generate_html(graph: SimilarityGraph, output_path: Path) -> None:
    """
    Generate interactive HTML visualization using pyvis.

    Falls back to simple HTML if pyvis not installed.
    """
    try:
        from pyvis.network import Network

        net = Network(height="800px", width="100%", bgcolor="#222222", font_color="white")  # pyright: ignore[reportArgumentType]
        net.barnes_hut()

        # Color by type
        type_colors = {
            "adr": "#6699cc",
            "code": "#66cc99",
            "doc": "#cc9966",
            "unknown": "#999999",
        }

        # Add nodes
        for node in graph.nodes.values():
            label = Path(node.id).name  # Just filename
            color = type_colors.get(node.type or "unknown", "#999999")
            net.add_node(node.id, label=label, color=color, title=node.id)

        # Add edges
        for edge in graph.edges:
            net.add_edge(edge.source, edge.target, value=edge.weight, title=f"{edge.weight:.2f}")

        net.save_graph(str(output_path))
        print(f"Graph saved to {output_path}")

    except ImportError:
        # Fallback to simple HTML with embedded JSON
        _generate_simple_html(graph, output_path)


def _generate_simple_html(graph: SimilarityGraph, output_path: Path) -> None:
    """Generate simple HTML visualization without pyvis."""
    graph_data = json.dumps(graph.to_dict(), indent=2)

    html = f"""<!DOCTYPE html>
<html>
<head>
    <title>Gundog Graph</title>
    <style>
        body {{ font-family: monospace; background: #222; color: #eee; padding: 20px; }}
        pre {{ background: #333; padding: 20px; overflow: auto; }}
    </style>
</head>
<body>
    <h1>Gundog Similarity Graph</h1>
    <p>Nodes: {len(graph.nodes)} | Edges: {len(graph.edges)}</p>
    <p>Install pyvis for interactive visualization: <code>pip install pyvis</code></p>
    <h2>Graph Data (JSON)</h2>
    <pre>{graph_data}</pre>
</body>
</html>"""

    output_path.write_text(html)
    print(f"Graph data saved to {output_path}")


def generate_json(graph: SimilarityGraph, output_path: Path) -> None:
    """Export graph as JSON."""
    with open(output_path, "w") as f:
        json.dump(graph.to_dict(), f, indent=2)
    print(f"Graph JSON saved to {output_path}")


def generate_dot(graph: SimilarityGraph, output_path: Path) -> None:
    """Export graph as Graphviz DOT."""
    output_path.write_text(graph.to_dot())
    print(f"Graph DOT saved to {output_path}")


def generate_query_graph(
    query: str,
    direct: list[dict],
    related: list[dict],
    output_path: Path,
) -> None:
    """
    Generate a focused graph visualization of query expansion.

    Shows only the direct matches and their related files.
    """
    try:
        from pyvis.network import Network

        net = Network(
            height="100vh",
            width="100%",
            bgcolor="#0d1117",
            font_color="#c9d1d9",  # pyright: ignore[reportArgumentType]
        )
        net.barnes_hut(gravity=-3000, spring_length=150)

        # Colors (GitHub dark theme inspired)
        colors = {
            "query": "#f78166",  # Orange-red for query
            "direct": "#58a6ff",  # Blue for direct matches
            "related": "#8b949e",  # Gray for related
            "adr": "#a371f7",  # Purple for ADRs
            "code": "#7ee787",  # Green for code
        }

        # Track added nodes
        added_nodes: set[str] = {"query"}

        # Add query node at center
        net.add_node(
            "query",
            label=query[:40] + ("..." if len(query) > 40 else ""),
            color=colors["query"],
            size=35,
            title=f"Query: {query}",
            shape="diamond",
            font={"size": 16, "color": "#ffffff"},
        )

        # Add direct matches
        for item in direct:
            path = item["path"]
            label = Path(path).name
            node_type = item.get("type", "")
            node_color = colors.get(node_type, colors["direct"])
            score = item.get("score", 0)
            lines = item.get("lines", "")
            title = f"{path}\nScore: {score:.3f}"
            if lines:
                title += f"\nLines: {lines}"

            net.add_node(
                path,
                label=label,
                color=node_color,
                size=22,
                title=title,
                borderWidth=2,
                font={"size": 12, "color": "#c9d1d9"},
            )
            added_nodes.add(path)
            net.add_edge("query", path, value=score, title=f"Score: {score:.3f}", color="#30363d")

        # Add related files
        for item in related:
            path = item["path"]
            via = item["via"]
            label = Path(path).name
            weight = item.get("edge_weight", 0)
            depth = item.get("depth", 1)

            title = f"{path}\nSimilarity: {weight:.3f}\nDepth: {depth}"

            if path not in added_nodes:
                net.add_node(
                    path,
                    label=label,
                    color=colors["related"],
                    size=14 if depth > 1 else 18,
                    title=title,
                    font={"size": 10, "color": "#8b949e"},
                )
                added_nodes.add(path)

            if via in added_nodes:
                net.add_edge(
                    via, path, value=weight, title=f"Similarity: {weight:.3f}", color="#21262d"
                )
            elif path in added_nodes:
                net.add_edge(
                    "query", path, value=weight, title=f"Similarity: {weight:.3f}", color="#21262d"
                )

        net.save_graph(str(output_path))

        # Post-process to inject custom styles and fix layout
        html = output_path.read_text()
        custom_style = """
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  html, body { height: 100%; overflow: hidden; background: #0d1117; }
  #mynetwork { border: none !important; height: 100vh !important; }
  .card { border: none !important; background: transparent !important; }
</style>
"""
        html = html.replace("<head>", f"<head>{custom_style}")
        html = html.replace("<center>", "").replace("</center>", "")
        # Remove any h1 headings pyvis adds
        html = re.sub(r"<h1>.*?</h1>", "", html)
        output_path.write_text(html)

    except ImportError:
        # Fallback: simple text representation
        html = f"""<!DOCTYPE html>
<html>
<head>
    <title>Query: {query}</title>
    <style>
        body {{ font-family: monospace; background: #1a1a2e; color: #eee; padding: 20px; }}
        .direct {{ color: #4ecdc4; }}
        .related {{ color: #95a5a6; }}
    </style>
</head>
<body>
    <h1>🔍 Query: {query}</h1>
    <h2 class="direct">Direct Matches ({len(direct)})</h2>
    <ul>{"".join(f"<li>{d['path']} (score: {d.get('score', 0):.3f})</li>" for d in direct)}</ul>
    <h2 class="related">Related via Graph ({len(related)})</h2>
    <ul>{"".join(f"<li>{r['path']} via {r['via']} (weight: {r.get('edge_weight', 0):.3f})</li>" for r in related)}</ul>
    <p><i>Install pyvis for interactive graph: pip install gundog[viz]</i></p>
</body>
</html>"""
        output_path.write_text(html)
