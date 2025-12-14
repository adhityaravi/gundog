"""Step definitions for chunking, hybrid search, exclusions, and scoring features."""

import os

from pytest_bdd import given, parsers, then, when

from gundog._chunker import parse_chunk_id
from gundog._indexer import Indexer
from gundog._query import QueryEngine
from gundog._templates import ExclusionTemplate
from tests.integration.steps.common import create_config, parse_datatable


# ============ Chunking Steps ============


@given(parsers.parse("chunking is enabled with max_tokens {max_tokens:d}"))
def enable_chunking(test_context, max_tokens):
    """Enable chunking with specified max tokens."""
    test_context["chunking_enabled"] = True
    test_context["chunking_max_tokens"] = max_tokens


@given("chunking is disabled")
def disable_chunking(test_context):
    """Disable chunking."""
    test_context["chunking_enabled"] = False


@then(parsers.parse('the index should contain multiple chunks for "{filename}"'))
def verify_multiple_chunks(test_context, filename):
    """Verify that a file was split into multiple chunks."""
    indexer = test_context["indexer"]
    all_ids = indexer.store.all_ids()

    # Count chunks for this file
    chunk_count = 0
    for doc_id in all_ids:
        parent_file, chunk_idx = parse_chunk_id(doc_id)
        if filename in parent_file and chunk_idx is not None:
            chunk_count += 1

    assert chunk_count > 1, f"Expected multiple chunks for {filename}, got {chunk_count}"


@then("the results should be deduplicated by file")
def verify_deduplication(test_context):
    """Verify that results are deduplicated by parent file."""
    result = test_context["query_result"]
    paths = [r["path"] for r in result.direct]
    # Check no duplicate paths
    assert len(paths) == len(set(paths)), "Results contain duplicate files"


# ============ Hybrid Search Steps ============


@given("hybrid search is enabled")
def enable_hybrid(test_context):
    """Enable hybrid search."""
    test_context["hybrid_enabled"] = True


@given("hybrid search is disabled")
def disable_hybrid(test_context):
    """Disable hybrid search."""
    test_context["hybrid_enabled"] = False


@then(parsers.parse('the results should include "{filename}"'))
def verify_results_include(test_context, filename):
    """Verify that results include a specific file."""
    result = test_context["query_result"]
    paths = [r["path"] for r in result.direct]
    matching = [p for p in paths if filename in p]
    assert matching, f"Expected {filename} in results, got {paths}"


@then(parsers.parse('the top result should be "{filename}"'))
def verify_top_result(test_context, filename):
    """Verify that the top result is a specific file."""
    result = test_context["query_result"]
    assert result.direct, "Expected at least one result"
    top_path = result.direct[0]["path"]
    assert filename in top_path, f"Expected top result to be {filename}, got {top_path}"


@then("I should get direct matches")
def verify_has_direct_matches(test_context):
    """Verify that the query returned direct matches."""
    result = test_context["query_result"]
    assert len(result.direct) > 0, "Expected direct matches but got none"


@then("the search should use vector similarity only")
def verify_vector_only_search(test_context):
    """Verify search completed (hybrid disabled means vector only)."""
    # This is more of a config verification - hybrid is disabled
    assert test_context["hybrid_enabled"] is False
    # Results should still exist (vector search works)
    result = test_context["query_result"]
    assert result is not None


# ============ Exclusion Steps ============


@given(parsers.parse('the exclusion template is "{template}"'))
def set_exclusion_template(test_context, template):
    """Set the exclusion template."""
    test_context["exclusion_template"] = ExclusionTemplate(template)


@given("custom exclude patterns")
def set_custom_excludes(test_context, datatable):
    """Set custom exclude patterns."""
    rows = parse_datatable(datatable)
    test_context["custom_excludes"] = [row["pattern"] for row in rows]


@given("a source directory with files")
def create_mixed_files(test_context, datatable):
    """Create files with various extensions."""
    rows = parse_datatable(datatable)
    for row in rows:
        filename = row["filename"]
        content = row["content"]

        # Determine directory based on extension
        if filename.endswith(".py") or "__pycache__" in filename:
            base_dir = test_context["src_dir"]
        else:
            base_dir = test_context["adr_dir"]

        filepath = base_dir / filename
        filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.write_text(content)


@when(parsers.parse('I delete the file "{filename}"'))
def delete_file(test_context, filename):
    """Delete a file from the source directory."""
    # Try both directories
    for base_dir in [test_context["adr_dir"], test_context["src_dir"]]:
        filepath = base_dir / filename
        if filepath.exists():
            os.remove(filepath)
            return
    raise FileNotFoundError(f"Could not find {filename} to delete")


@then(parsers.parse('the index should contain "{filename}"'))
def verify_index_contains(test_context, filename):
    """Verify the index contains a specific file."""
    indexer = test_context["indexer"]
    all_ids = indexer.store.all_ids()
    matching = [id for id in all_ids if filename in id]
    assert matching, f"Expected {filename} in index, got {all_ids}"


@then(parsers.parse('the index should not contain "{filename}"'))
def verify_index_not_contains(test_context, filename):
    """Verify the index does not contain a specific file."""
    indexer = test_context["indexer"]
    all_ids = indexer.store.all_ids()
    matching = [id for id in all_ids if filename in id]
    assert not matching, f"Did not expect {filename} in index, but found {matching}"


# ============ Scoring Steps ============


@when(parsers.parse('I query for "{query_text}" with min_score {min_score:f}'))
def query_with_min_score(test_context, query_text, min_score):
    """Execute a query with a specific min_score threshold."""
    config = create_config(test_context)
    test_context["config"] = config
    engine = QueryEngine(config)
    test_context["query_engine"] = engine
    result = engine.query(query_text, min_score=min_score)
    test_context["query_result"] = result


@then("I should get no direct matches")
def verify_no_matches(test_context):
    """Verify query returned no direct matches."""
    result = test_context["query_result"]
    assert len(result.direct) == 0, f"Expected no matches, got {len(result.direct)}"


@then("all scores should be between 0 and 1")
def verify_score_range(test_context):
    """Verify all scores are in valid range."""
    result = test_context["query_result"]
    for item in result.direct:
        score = item["score"]
        assert 0 <= score <= 1, f"Score {score} out of range [0, 1]"


@then("results should only include matches above threshold")
def verify_threshold_filtering(test_context):
    """Verify all results meet the threshold (scores are rescaled, so > 0)."""
    result = test_context["query_result"]
    for item in result.direct:
        # Rescaled scores: anything returned should be > 0
        assert item["score"] > 0, f"Score {item['score']} should be above 0 (rescaled)"
