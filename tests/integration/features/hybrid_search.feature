Feature: Hybrid Search
  As a developer
  I want to combine semantic and keyword search
  So that I find both conceptually related and exact matches

  Background:
    Given a clean gundog environment

  Scenario: Hybrid search finds exact keyword matches
    Given hybrid search is enabled
    And a source directory with markdown files
      | filename          | content                                      |
      | auth-service.md   | The AuthenticationService handles login      |
      | user-mgmt.md      | User management and access control           |
      | config.md         | Configuration settings for the application   |
    And I run gundog index
    When I query for "AuthenticationService"
    Then the top result should be "auth-service.md"

  Scenario: Hybrid search combines semantic and keyword
    Given hybrid search is enabled
    And a source directory with markdown files
      | filename       | content                                           |
      | jwt-auth.md    | JWT token authentication for secure API access    |
      | password.md    | Password hashing and validation utilities         |
      | sessions.md    | User session management and cookies               |
    And I run gundog index
    When I query for "authentication security"
    Then I should get direct matches
    And the results should include "jwt-auth.md"

  Scenario: Hybrid search disabled uses only vector search
    Given hybrid search is disabled
    And a source directory with markdown files
      | filename       | content                                   |
      | exact.md       | ExactMatchKeyword in the document         |
      | similar.md     | Related concepts and ideas                |
    And I run gundog index
    When I query for "ExactMatchKeyword"
    Then the search should use vector similarity only
