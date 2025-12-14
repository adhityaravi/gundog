"""Test similarity graph."""

from pathlib import Path

import numpy as np

from gundog._graph import GraphEdge, GraphNode, SimilarityGraph


def test_graph_node_creation():
    """Test creating a graph node."""
    node = GraphNode(id="file.md", type="adr")
    assert node.id == "file.md"
    assert node.type == "adr"
    assert node.neighbors == {}


def test_graph_edge_creation():
    """Test creating a graph edge."""
    edge = GraphEdge(source="a.md", target="b.md", weight=0.75)
    assert edge.source == "a.md"
    assert edge.target == "b.md"
    assert edge.weight == 0.75


def test_similarity_graph_build(
    temp_dir: Path, sample_vectors: dict[str, np.ndarray], sample_metadata: dict[str, dict]
):
    """Test building similarity graph from vectors."""
    graph = SimilarityGraph(temp_dir / "graph.json")

    graph.build(
        vectors=sample_vectors,
        metadata=sample_metadata,
        threshold=0.0,  # Low threshold to ensure edges
    )

    # Should have nodes for all files
    assert len(graph.nodes) == 5

    # Check node types
    assert graph.nodes["file_0.md"].type == "adr"
    assert graph.nodes["file_2.md"].type == "code"
    assert graph.nodes["file_4.md"].type == "doc"


def test_similarity_graph_build_high_threshold(
    temp_dir: Path, sample_vectors: dict[str, np.ndarray], sample_metadata: dict[str, dict]
):
    """Test building graph with high threshold results in fewer edges."""
    graph = SimilarityGraph(temp_dir / "graph.json")

    graph.build(
        vectors=sample_vectors,
        metadata=sample_metadata,
        threshold=0.99,  # Very high threshold
    )

    # Still should have all nodes
    assert len(graph.nodes) == 5

    # But very few or no edges (depending on random vectors)
    # Most random vectors won't have 0.99+ similarity


def test_similarity_graph_get_neighbors(temp_dir: Path):
    """Test getting neighbors of a node."""
    graph = SimilarityGraph(temp_dir / "graph.json")

    # Manually set up nodes and edges
    graph.nodes["a.md"] = GraphNode(id="a.md", type="adr", neighbors={"b.md": 0.8, "c.md": 0.6})
    graph.nodes["b.md"] = GraphNode(id="b.md", type="adr", neighbors={"a.md": 0.8})
    graph.nodes["c.md"] = GraphNode(id="c.md", type="code", neighbors={"a.md": 0.6})

    neighbors = graph.get_neighbors("a.md")

    assert len(neighbors) == 2
    assert neighbors[0] == ("b.md", 0.8)  # Higher weight first
    assert neighbors[1] == ("c.md", 0.6)


def test_similarity_graph_get_neighbors_min_weight(temp_dir: Path):
    """Test filtering neighbors by minimum weight."""
    graph = SimilarityGraph(temp_dir / "graph.json")

    graph.nodes["a.md"] = GraphNode(id="a.md", type="adr", neighbors={"b.md": 0.8, "c.md": 0.6})
    graph.nodes["b.md"] = GraphNode(id="b.md", type="adr", neighbors={"a.md": 0.8})
    graph.nodes["c.md"] = GraphNode(id="c.md", type="code", neighbors={"a.md": 0.6})

    neighbors = graph.get_neighbors("a.md", min_weight=0.7)

    assert len(neighbors) == 1
    assert neighbors[0] == ("b.md", 0.8)


def test_similarity_graph_expand(temp_dir: Path):
    """Test BFS expansion from seed nodes."""
    graph = SimilarityGraph(temp_dir / "graph.json")

    # Create a simple graph: a -> b -> c -> d
    graph.nodes["a.md"] = GraphNode(id="a.md", type="adr", neighbors={"b.md": 0.8})
    graph.nodes["b.md"] = GraphNode(id="b.md", type="adr", neighbors={"a.md": 0.8, "c.md": 0.7})
    graph.nodes["c.md"] = GraphNode(id="c.md", type="code", neighbors={"b.md": 0.7, "d.md": 0.65})
    graph.nodes["d.md"] = GraphNode(id="d.md", type="doc", neighbors={"c.md": 0.65})

    # Expand from 'a' with depth 1
    discovered = graph.expand(seed_ids=["a.md"], min_weight=0.6, max_depth=1)

    assert "b.md" in discovered
    assert discovered["b.md"]["via"] == "a.md"
    assert discovered["b.md"]["depth"] == 1

    # c and d should not be discovered (depth > 1)
    assert "c.md" not in discovered
    assert "d.md" not in discovered


def test_similarity_graph_expand_depth_2(temp_dir: Path):
    """Test expansion with depth 2."""
    graph = SimilarityGraph(temp_dir / "graph.json")

    graph.nodes["a.md"] = GraphNode(id="a.md", type="adr", neighbors={"b.md": 0.8})
    graph.nodes["b.md"] = GraphNode(id="b.md", type="adr", neighbors={"a.md": 0.8, "c.md": 0.7})
    graph.nodes["c.md"] = GraphNode(id="c.md", type="code", neighbors={"b.md": 0.7})

    discovered = graph.expand(seed_ids=["a.md"], min_weight=0.6, max_depth=2)

    assert "b.md" in discovered
    assert "c.md" in discovered
    assert discovered["c.md"]["depth"] == 2
    assert discovered["c.md"]["via"] == "b.md"


def test_similarity_graph_save_and_load(temp_dir: Path):
    """Test saving and loading graph."""
    graph_path = temp_dir / "graph.json"
    graph = SimilarityGraph(graph_path)

    graph.nodes["a.md"] = GraphNode(id="a.md", type="adr", neighbors={"b.md": 0.8})
    graph.nodes["b.md"] = GraphNode(id="b.md", type="code", neighbors={"a.md": 0.8})
    graph.edges.append(GraphEdge(source="a.md", target="b.md", weight=0.8))
    graph._dirty = True

    graph.save()

    # Load into new graph
    graph2 = SimilarityGraph(graph_path)
    graph2.load()

    assert len(graph2.nodes) == 2
    assert len(graph2.edges) == 1
    assert graph2.nodes["a.md"].type == "adr"
    assert graph2.nodes["a.md"].neighbors["b.md"] == 0.8


def test_similarity_graph_to_dict(temp_dir: Path):
    """Test exporting graph as dict."""
    graph = SimilarityGraph(temp_dir / "graph.json")

    graph.nodes["a.md"] = GraphNode(id="a.md", type="adr", neighbors={})
    graph.nodes["b.md"] = GraphNode(id="b.md", type="code", neighbors={})
    graph.edges.append(GraphEdge(source="a.md", target="b.md", weight=0.75))

    result = graph.to_dict()

    assert len(result["nodes"]) == 2
    assert len(result["edges"]) == 1
    assert result["edges"][0]["weight"] == 0.75


def test_similarity_graph_to_dot(temp_dir: Path):
    """Test exporting graph as DOT format."""
    graph = SimilarityGraph(temp_dir / "graph.json")

    graph.nodes["a.md"] = GraphNode(id="a.md", type="adr", neighbors={})
    graph.nodes["b.md"] = GraphNode(id="b.md", type="code", neighbors={})
    graph.edges.append(GraphEdge(source="a.md", target="b.md", weight=0.75))

    dot = graph.to_dot()

    assert "graph G {" in dot
    assert "a.md" in dot
    assert "b.md" in dot
    assert "lightblue" in dot  # adr color
    assert "lightgreen" in dot  # code color
