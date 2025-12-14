Feature: Score Rescaling
  As a developer
  I want scores to be intuitive
  So that I can understand result relevance at a glance

  Background:
    Given a clean gundog environment

  Scenario: Irrelevant queries return no results
    Given a source directory with markdown files
      | filename       | content                                    |
      | auth.md        | Authentication using JWT tokens            |
      | database.md    | PostgreSQL database configuration          |
    And I run gundog index
    When I query for "pizza recipe ingredients"
    Then I should get no direct matches

  Scenario: Relevant queries return results with meaningful scores
    Given a source directory with markdown files
      | filename       | content                                    |
      | jwt-auth.md    | JWT authentication tokens for API access   |
      | oauth.md       | OAuth2 authorization flow implementation   |
    And I run gundog index
    When I query for "JWT authentication"
    Then I should get direct matches
    And all scores should be between 0 and 1

  Scenario: Min score threshold filters weak matches
    Given a source directory with markdown files
      | filename       | content                                    |
      | auth.md        | Authentication system design               |
      | unrelated.md   | Completely different topic about cooking   |
    And I run gundog index
    When I query for "authentication" with min_score 0.6
    Then results should only include matches above threshold
