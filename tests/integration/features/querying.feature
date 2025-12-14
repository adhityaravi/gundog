Feature: Semantic Search
  As a developer
  I want to search my documents semantically
  So that I can find relevant information quickly

  Background:
    Given a clean gundog environment
    And a source directory with markdown files
      | filename          | content                                           |
      | auth-design.md    | Authentication using JWT tokens and OAuth2        |
      | db-schema.md      | PostgreSQL database schema with user tables       |
      | api-endpoints.md  | REST API endpoints for user management            |
    And I run gundog index

  Scenario: Search returns relevant results
    When I query for "user authentication"
    Then I should get direct matches
    And the top result should be "auth-design.md"

  Scenario: Search with type filter
    Given a source directory with python files
      | filename   | content                    |
      | auth.py    | JWT token validation       |
    And I run gundog index
    When I query for "authentication" with type filter "code"
    Then all results should have type "code"

  Scenario: Search with graph expansion
    Given a source directory with markdown files
      | filename            | content                                                    |
      | jwt-login.md        | JWT login authentication for secure user access            |
      | auth-tokens.md      | Authentication tokens and JWT mechanisms for user login    |
      | token-session.md    | User session tokens for authentication and login           |
      | session-mgmt.md     | Session management with authentication tokens              |
      | user-sessions.md    | Managing user sessions with token authentication           |
    And I run gundog index
    When I query for "JWT login" with top 2 results with expansion enabled
    Then I should get direct matches
    And I should get related matches via graph

  Scenario: Search without graph expansion
    When I query for "authentication" with expansion disabled
    Then I should get direct matches
    And I should not get related matches

  Scenario: Search with custom top-k
    When I query for "user" with top 2 results
    Then I should get at most 2 direct matches
