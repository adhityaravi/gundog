"""Step definitions for storage features."""

from pytest_bdd import given, parsers, then, when

from gundog._store import create_store
from tests.integration.steps.common import generate_random_vector, parse_datatable


@given(parsers.parse('I store a vector with id "{doc_id}" and metadata'))
def store_vector_with_metadata(test_context, doc_id, datatable):
    """Store a vector with the given metadata."""
    if test_context["store"] is None:
        test_context["store"] = create_store(
            test_context["backend"],
            test_context["index_dir"],
        )

    rows = parse_datatable(datatable)
    metadata = {row["key"]: row["value"] for row in rows}
    vector = generate_random_vector(seed=hash(doc_id) % 2**32)
    test_context["vectors"][doc_id] = vector
    test_context["store"].upsert(doc_id, vector, metadata)


@given("I store multiple vectors")
def store_multiple_vectors(test_context, datatable):
    """Store multiple vectors with metadata."""
    if test_context["store"] is None:
        test_context["store"] = create_store(
            test_context["backend"],
            test_context["index_dir"],
        )

    rows = parse_datatable(datatable)
    for row in rows:
        doc_id = row["id"]
        metadata = {"type": row["type"]}
        vector = generate_random_vector(seed=hash(doc_id) % 2**32)
        test_context["vectors"][doc_id] = vector
        test_context["store"].upsert(doc_id, vector, metadata)


@given("I save the store")
def save_store(test_context):
    """Save the store to disk."""
    test_context["store"].save()


@when(parsers.parse('I retrieve the vector with id "{doc_id}"'))
def retrieve_vector(test_context, doc_id):
    """Retrieve a vector by ID."""
    test_context["retrieved"] = test_context["store"].get(doc_id)


@when(parsers.parse('I delete the vector with id "{doc_id}"'))
def delete_vector(test_context, doc_id):
    """Delete a vector by ID."""
    test_context["store"].delete(doc_id)


@when("I search with a query vector")
def search_vectors(test_context):
    """Search for similar vectors."""
    query_vector = generate_random_vector(seed=42)
    test_context["search_results"] = test_context["store"].search(query_vector, top_k=10)


@when("I create a new store instance and load")
def create_new_store_and_load(test_context):
    """Create a new store instance and load from disk."""
    test_context["store"] = create_store(
        test_context["backend"],
        test_context["index_dir"],
    )
    test_context["store"].load()


@then("the vector should exist")
def verify_vector_exists(test_context):
    """Verify that the retrieved vector exists."""
    assert test_context["retrieved"] is not None


@then("the vector should not exist")
def verify_vector_not_exists(test_context):
    """Verify that the vector does not exist."""
    retrieved = test_context["store"].get("doc1")
    assert retrieved is None


@then(parsers.parse('the metadata should contain "{key}" with value "{value}"'))
def verify_metadata(test_context, key, value):
    """Verify metadata contains expected key-value pair."""
    _, metadata = test_context["retrieved"]
    assert key in metadata
    assert metadata[key] == value


@then("I should get ranked results")
def verify_ranked_results(test_context):
    """Verify search returned ranked results."""
    results = test_context["search_results"]
    assert len(results) > 0
    # Verify results are sorted by score descending
    scores = [r.score for r in results]
    assert scores == sorted(scores, reverse=True)


@then(parsers.parse('the vector with id "{doc_id}" should exist'))
def verify_specific_vector_exists(test_context, doc_id):
    """Verify a specific vector exists in the store."""
    result = test_context["store"].get(doc_id)
    assert result is not None
