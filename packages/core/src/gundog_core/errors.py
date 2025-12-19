"""Shared error types for gundog.

All gundog packages use these exceptions for consistent error handling.
"""


class GundogError(Exception):
    """Base exception for all gundog errors."""

    pass


class ConnectionError(GundogError):
    """Failed to connect to the gundog daemon.

    Raised when:
    - Daemon is not running
    - Network connection fails
    - Connection times out
    """

    pass


class QueryError(GundogError):
    """Query execution failed.

    Raised when:
    - Invalid query parameters
    - Server-side query error
    - Timeout during query execution
    """

    pass


class IndexNotFoundError(GundogError):
    """Requested index does not exist.

    Raised when:
    - Querying a non-existent index
    - Switching to an unknown index
    """

    pass


class AuthenticationError(GundogError):
    """Authentication failed.

    Raised when:
    - Invalid or missing API key
    - Token expired
    """

    pass


class ConfigError(GundogError):
    """Configuration error.

    Raised when:
    - Invalid config file format
    - Missing required config values
    - Config file not found (when required)
    """

    pass
