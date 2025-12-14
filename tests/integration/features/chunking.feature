Feature: Text Chunking
  As a developer
  I want to split large files into chunks
  So that I get better search results for specific sections

  Background:
    Given a clean gundog environment

  Scenario: Chunking splits large files
    Given chunking is enabled with max_tokens 50
    And a source directory with markdown files
      | filename   | content                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |
      | large.md   | First section about authentication and login systems. This covers JWT tokens and OAuth2 flows for secure access to APIs. We implement refresh tokens and session management. Second section about database design and architecture. This covers PostgreSQL schemas and indexing strategies for optimal performance. We discuss normalization and query optimization. Third section about API design patterns. This covers REST endpoints and versioning strategies. We implement rate limiting and caching. Fourth section about deployment. This covers containerization with Docker and orchestration with Kubernetes. |
    When I run gundog index
    Then the index should contain multiple chunks for "large.md"

  Scenario: Chunking disabled keeps files whole
    Given chunking is disabled
    And a source directory with markdown files
      | filename   | content                                         |
      | doc.md     | A simple document about authentication systems. |
    When I run gundog index
    Then the index should contain 1 documents

  Scenario: Search returns best chunk per file
    Given chunking is enabled with max_tokens 50
    And a source directory with markdown files
      | filename   | content                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |
      | large.md   | First section about authentication and login systems. This covers JWT tokens and OAuth2 flows for secure access to APIs. We implement refresh tokens and session management. Second section about database design and architecture. This covers PostgreSQL schemas and indexing strategies for optimal performance. We discuss normalization and query optimization. Third section about API design patterns. This covers REST endpoints and versioning strategies. We implement rate limiting and caching. Fourth section about deployment. This covers containerization with Docker and orchestration with Kubernetes. |
    And I run gundog index
    When I query for "database schema"
    Then the results should be deduplicated by file
