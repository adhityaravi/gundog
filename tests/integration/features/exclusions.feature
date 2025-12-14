Feature: Exclusion Patterns
  As a developer
  I want to exclude certain files from indexing
  So that I don't pollute the index with generated or irrelevant files

  Background:
    Given a clean gundog environment

  Scenario: Exclusion template filters Python artifacts
    Given the exclusion template is "python"
    And a source directory with files
      | filename              | content                    |
      | main.py               | Main application code      |
      | __init__.py           | Package init              |
      | __pycache__/cache.pyc | Compiled bytecode         |
      | conftest.py           | Pytest configuration      |
    When I run gundog index
    Then the index should contain 1 documents
    And the index should not contain "__init__.py"
    And the index should not contain "conftest.py"

  Scenario: Custom exclude patterns work
    Given custom exclude patterns
      | pattern       |
      | **/test_*.md  |
      | **/draft_*    |
    And a source directory with markdown files
      | filename      | content              |
      | readme.md     | Project readme       |
      | test_api.md   | API tests            |
      | draft_spec.md | Draft specification  |
    When I run gundog index
    Then the index should contain 1 documents
    And the index should contain "readme.md"

  Scenario: File removal is detected on reindex
    Given a source directory with markdown files
      | filename   | content        |
      | keep.md    | Keep this file |
      | remove.md  | Remove this    |
    And I run gundog index
    When I delete the file "remove.md"
    And I run gundog index
    Then the index should contain 1 documents
    And the index should not contain "remove.md"
