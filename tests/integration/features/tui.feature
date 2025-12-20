Feature: TUI Application
  As a gundog user
  I want to use the TUI interface
  So that I can search my codebase interactively

  Scenario: TUI app starts with correct initial state
    Given a TUI app instance
    When the app is mounted
    Then the app should display the title "ｇｕｎｄｏｇ"
    And the search input should be visible
    And the footer should show keyboard hints

  Scenario: Focus search input with slash key
    Given a TUI app instance
    When the app is mounted
    And I press "slash"
    Then the search input should be focused

  Scenario: Show help with question mark key
    Given a TUI app instance
    When the app is mounted
    And I press "question_mark"
    Then the preview header should show "KEYBINDINGS"

  Scenario: Toggle help off with question mark
    Given a TUI app instance
    When the app is mounted
    And I press "question_mark"
    And I press "question_mark"
    Then the preview header should show "Preview"

  Scenario: Escape key unfocuses search
    Given a TUI app instance
    When the app is mounted
    And I press "slash"
    And I press "escape"
    Then the search input should not be focused

  Scenario: Quit app with q key
    Given a TUI app instance
    When the app is mounted
    And I press "q"
    Then the app should be exiting

  Scenario: Navigate results with j key
    Given a TUI app instance with mock results
    When the app is mounted
    And I press "j"
    Then the selected index should be 1

  Scenario: Navigate results with k key
    Given a TUI app instance with mock results
    When the app is mounted
    And I press "j"
    And I press "k"
    Then the selected index should be 0

  Scenario: Go to first result with g key
    Given a TUI app instance with mock results
    When the app is mounted
    And I press "j"
    And I press "j"
    And I press "g"
    Then the selected index should be 0

  Scenario: Show index selection with i key
    Given a TUI app instance with mock indexes
    When the app is mounted
    And I press "i"
    Then the preview header should show "SELECT INDEX"

  Scenario: Connection state shows in footer
    Given a TUI app instance
    When the app is mounted
    Then the footer should show connection status

  Scenario: Direct and related sections are visible
    Given a TUI app instance
    When the app is mounted
    Then the direct section header should be visible
    And the related section header should be visible

  Scenario: Graph pane is visible
    Given a TUI app instance
    When the app is mounted
    Then the graph pane should be visible

  Scenario: Type in search input
    Given a TUI app instance
    When the app is mounted
    And I press "slash"
    And I type "authentication"
    Then the search input should contain "authentication"
