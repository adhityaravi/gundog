Feature: Document Indexing
  As a developer
  I want to index my documents and code
  So that I can search them semantically

  Background:
    Given a clean gundog environment

  Scenario: Index markdown files
    Given a source directory with markdown files
      | filename     | content                          |
      | adr-001.md   | Architecture decision for auth   |
      | adr-002.md   | Database schema design choices   |
    When I run gundog index
    Then the index should contain 2 documents
    And the graph should have nodes for each document

  Scenario: Index Python files
    Given a source directory with python files
      | filename   | content                              |
      | auth.py    | def authenticate(user): pass         |
      | db.py      | class Database: pass                 |
    When I run gundog index
    Then the index should contain 2 documents

  Scenario: Incremental indexing skips unchanged files
    Given a source directory with markdown files
      | filename   | content              |
      | doc1.md    | First document       |
    And I run gundog index
    When I add a new file "doc2.md" with content "Second document"
    And I run gundog index
    Then the index should contain 2 documents
    And the indexing summary should show 1 indexed and 1 skipped

  Scenario: Rebuild index from scratch
    Given a source directory with markdown files
      | filename   | content              |
      | doc1.md    | First document       |
    And I run gundog index
    When I run gundog index with rebuild
    Then the indexing summary should show 1 indexed and 0 skipped
