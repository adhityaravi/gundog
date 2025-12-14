"""Step definitions for querying features."""

from pathlib import Path

from pytest_bdd import parsers, then, when

from gundog._query import QueryEngine
from tests.integration.steps.common import create_config


@when(parsers.parse('I query for "{query_text}"'))
def run_query(test_context, query_text):
    """Run a semantic query."""
    config = create_config(test_context)
    engine = QueryEngine(config)
    test_context["query_engine"] = engine
    test_context["query_result"] = engine.query(query_text)


@when(parsers.parse('I query for "{query_text}" with type filter "{type_filter}"'))
def run_query_with_type(test_context, query_text, type_filter):
    """Run a semantic query with type filter."""
    config = create_config(test_context)
    engine = QueryEngine(config)
    test_context["query_engine"] = engine
    test_context["query_result"] = engine.query(query_text, type_filter=type_filter)


@when(parsers.parse('I query for "{query_text}" with expansion enabled'))
def run_query_with_expansion(test_context, query_text):
    """Run a semantic query with graph expansion."""
    config = create_config(test_context)
    engine = QueryEngine(config)
    test_context["query_engine"] = engine
    test_context["query_result"] = engine.query(query_text, expand=True)


@when(parsers.parse('I query for "{query_text}" with expansion disabled'))
def run_query_without_expansion(test_context, query_text):
    """Run a semantic query without graph expansion."""
    config = create_config(test_context)
    engine = QueryEngine(config)
    test_context["query_engine"] = engine
    test_context["query_result"] = engine.query(query_text, expand=False)


@when(parsers.parse('I query for "{query_text}" with top {top_k:d} results'))
def run_query_with_top_k(test_context, query_text, top_k):
    """Run a semantic query with custom top-k."""
    config = create_config(test_context)
    engine = QueryEngine(config)
    test_context["query_engine"] = engine
    test_context["query_result"] = engine.query(query_text, top_k=top_k)


@when(
    parsers.parse('I query for "{query_text}" with top {top_k:d} results with expansion enabled')
)
def run_query_with_top_k_and_expansion(test_context, query_text, top_k):
    """Run a semantic query with custom top-k and graph expansion."""
    config = create_config(test_context)
    engine = QueryEngine(config)
    test_context["query_engine"] = engine
    test_context["query_result"] = engine.query(query_text, top_k=top_k, expand=True)


@then("I should get direct matches")
def verify_direct_matches(test_context):
    """Verify that query returned direct matches."""
    result = test_context["query_result"]
    assert len(result.direct) > 0


@then(parsers.parse('the top result should be "{filename}"'))
def verify_top_result(test_context, filename):
    """Verify the top result matches expected filename."""
    result = test_context["query_result"]
    assert len(result.direct) > 0
    top_path = Path(result.direct[0]["path"]).name
    assert top_path == filename


@then(parsers.parse('all results should have type "{expected_type}"'))
def verify_result_types(test_context, expected_type):
    """Verify all results have the expected type."""
    result = test_context["query_result"]
    for item in result.direct:
        assert item["type"] == expected_type


@then("I should get related matches via graph")
def verify_related_matches(test_context):
    """Verify that query returned related matches."""
    result = test_context["query_result"]
    assert len(result.related) > 0


@then("I should not get related matches")
def verify_no_related_matches(test_context):
    """Verify that query did not return related matches."""
    result = test_context["query_result"]
    assert len(result.related) == 0


@then(parsers.parse("I should get at most {max_count:d} direct matches"))
def verify_max_direct_matches(test_context, max_count):
    """Verify the number of direct matches is within limit."""
    result = test_context["query_result"]
    assert len(result.direct) <= max_count
