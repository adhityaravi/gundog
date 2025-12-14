Feature: LanceDB Vector Store
  As a developer
  I want to use the LanceDB backend for vector storage
  So that I can handle large-scale document collections

  Background:
    Given a clean gundog environment
    And the storage backend is "lancedb"

  @requires_lancedb
  Scenario: Store and retrieve vectors
    Given I store a vector with id "doc1" and metadata
      | key   | value |
      | type  | adr   |
    When I retrieve the vector with id "doc1"
    Then the vector should exist
    And the metadata should contain "type" with value "adr"

  @requires_lancedb
  Scenario: Search for similar vectors
    Given I store multiple vectors
      | id    | type |
      | doc1  | adr  |
      | doc2  | adr  |
      | doc3  | code |
    When I search with a query vector
    Then I should get ranked results

  @requires_lancedb
  Scenario: Delete vectors
    Given I store a vector with id "doc1" and metadata
      | key   | value |
      | type  | adr   |
    When I delete the vector with id "doc1"
    Then the vector should not exist

  @requires_lancedb
  Scenario: Persistence across sessions
    Given I store a vector with id "doc1" and metadata
      | key   | value |
      | type  | adr   |
    And I save the store
    When I create a new store instance and load
    Then the vector with id "doc1" should exist
