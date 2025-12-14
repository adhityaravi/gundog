Feature: NumPy Vector Store
  As a developer
  I want to use the numpy backend for vector storage
  So that I can index and search without extra dependencies

  Background:
    Given a clean gundog environment
    And the storage backend is "numpy"

  Scenario: Store and retrieve vectors
    Given I store a vector with id "doc1" and metadata
      | key   | value |
      | type  | adr   |
    When I retrieve the vector with id "doc1"
    Then the vector should exist
    And the metadata should contain "type" with value "adr"

  Scenario: Search for similar vectors
    Given I store multiple vectors
      | id    | type |
      | doc1  | adr  |
      | doc2  | adr  |
      | doc3  | code |
    When I search with a query vector
    Then I should get ranked results

  Scenario: Delete vectors
    Given I store a vector with id "doc1" and metadata
      | key   | value |
      | type  | adr   |
    When I delete the vector with id "doc1"
    Then the vector should not exist

  Scenario: Persistence across sessions
    Given I store a vector with id "doc1" and metadata
      | key   | value |
      | type  | adr   |
    And I save the store
    When I create a new store instance and load
    Then the vector with id "doc1" should exist
