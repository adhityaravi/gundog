"""Step definitions for indexing features."""

from pytest_bdd import given, parsers, then, when

from gundog._indexer import Indexer
from tests.integration.steps.common import create_config, parse_datatable


@given(parsers.parse("a source directory with markdown files"))
def create_markdown_files(test_context, datatable):
    """Create markdown files in the ADR directory."""
    rows = parse_datatable(datatable)
    for row in rows:
        filepath = test_context["adr_dir"] / row["filename"]
        filepath.write_text(row["content"])


@given(parsers.parse("a source directory with python files"))
def create_python_files(test_context, datatable):
    """Create Python files in the src directory."""
    rows = parse_datatable(datatable)
    for row in rows:
        filepath = test_context["src_dir"] / row["filename"]
        filepath.write_text(row["content"])


@given(parsers.parse('I add a new file "{filename}" with content "{content}"'))
@when(parsers.parse('I add a new file "{filename}" with content "{content}"'))
def add_new_file(test_context, filename, content):
    """Add a new file to the appropriate directory."""
    if filename.endswith(".md"):
        filepath = test_context["adr_dir"] / filename
    else:
        filepath = test_context["src_dir"] / filename
    filepath.write_text(content)


@when("I run gundog index")
@given("I run gundog index")
def run_index(test_context):
    """Run the indexer."""
    config = create_config(test_context)
    test_context["config"] = config
    indexer = Indexer(config)
    test_context["indexer"] = indexer
    test_context["index_summary"] = indexer.index(rebuild=False)


@when("I run gundog index with rebuild")
def run_index_rebuild(test_context):
    """Run the indexer with rebuild flag."""
    config = create_config(test_context)
    test_context["config"] = config
    indexer = Indexer(config)
    test_context["indexer"] = indexer
    test_context["index_summary"] = indexer.index(rebuild=True)


@then(parsers.parse("the index should contain {count:d} documents"))
def verify_index_count(test_context, count):
    """Verify the number of documents in the index."""
    indexer = test_context["indexer"]
    assert len(indexer.store.all_ids()) == count


@then("the graph should have nodes for each document")
def verify_graph_nodes(test_context):
    """Verify the graph has nodes for all indexed documents."""
    indexer = test_context["indexer"]
    doc_count = len(indexer.store.all_ids())
    node_count = len(indexer.graph.nodes)
    assert node_count == doc_count


@then(
    parsers.parse("the indexing summary should show {indexed:d} indexed and {skipped:d} skipped")
)
def verify_index_summary(test_context, indexed, skipped):
    """Verify the indexing summary."""
    summary = test_context["index_summary"]
    assert summary["files_indexed"] == indexed
    assert summary["files_skipped"] == skipped
