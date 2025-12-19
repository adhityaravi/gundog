Feature: WebSocket Communication
  As a TUI client developer
  I want to communicate with the daemon via WebSocket
  So that I can stream search results in real-time

  Background:
    Given a clean gundog environment
    And a source directory with markdown files
      | filename          | content                                           |
      | auth-design.md    | Authentication using JWT tokens and OAuth2        |
      | db-schema.md      | PostgreSQL database schema with user tables       |
    And I run gundog index
    And the daemon is running

  Scenario: Query via WebSocket returns results
    When I send a WebSocket query for "authentication"
    Then I should receive a query_result message
    And the result should contain direct matches

  Scenario: List indexes via WebSocket
    When I send a WebSocket list_indexes request
    Then I should receive an index_list message
    And the list should contain the test index

  Scenario: Switch index via WebSocket
    When I send a WebSocket switch_index request for the test index
    Then I should receive an index_switched message

  Scenario: Invalid message type returns error
    When I send a WebSocket message with unknown type "invalid_type"
    Then I should receive an error message with code "INVALID_REQUEST"

  Scenario: Query without text returns error
    When I send a WebSocket query with empty text
    Then I should receive an error message with code "INVALID_REQUEST"
