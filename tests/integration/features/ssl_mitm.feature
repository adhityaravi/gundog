Feature: SSL MITM Proxy Support
  As a developer on a corporate network
  I want gundog to work through SSL-intercepting proxies
  So that I can use it behind enterprise security infrastructure

  Background:
    Given a MITM proxy environment

  Scenario: HTTPS requests fail without SSL fix
    When I make a direct HTTPS request to HuggingFace
    Then the request should fail with an SSL error

  Scenario: HTTPS requests work with SSL verification disabled
    Given SSL verification is disabled
    When I make a direct HTTPS request to HuggingFace
    Then the request should succeed

  Scenario: HuggingFace Hub works with SSL fix
    Given SSL verification is disabled
    When I fetch model info from HuggingFace Hub
    Then the model info should be retrieved successfully
