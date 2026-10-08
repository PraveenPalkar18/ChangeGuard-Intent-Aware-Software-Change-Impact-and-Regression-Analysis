"""Custom exception hierarchy for ChangeGuard."""
from typing import Optional


class ChangeGuardException(Exception):
    """Base exception class for all ChangeGuard errors."""

    def __init__(self, message: str, status_code: int = 500, details: Optional[dict] = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.details = details or {}


class InvalidInputException(ChangeGuardException):
    """Raised when client input validation fails."""

    def __init__(self, message: str, details: Optional[dict] = None):
        super().__init__(message=message, status_code=400, details=details)


class GitHubAuthenticationException(ChangeGuardException):
    """Raised when GitHub token authentication fails (401)."""

    def __init__(self, message: str = "Invalid or expired GitHub authentication token.", details: Optional[dict] = None):
        super().__init__(message=message, status_code=401, details=details)


class GitHubResourceNotFoundException(ChangeGuardException):
    """Raised when the requested repository or PR does not exist or is private without token (404)."""

    def __init__(self, message: str = "Requested GitHub repository or Pull Request not found.", details: Optional[dict] = None):
        super().__init__(message=message, status_code=404, details=details)


class GitHubRateLimitExceededException(ChangeGuardException):
    """Raised when GitHub API rate limits are exhausted (403/429)."""

    def __init__(self, message: str = "GitHub API rate limit exceeded.", details: Optional[dict] = None):
        super().__init__(message=message, status_code=429, details=details)


class GitHubAPIException(ChangeGuardException):
    """Raised when unexpected errors occur during GitHub API communication."""

    def __init__(self, message: str = "GitHub API service error.", status_code: int = 502, details: Optional[dict] = None):
        super().__init__(message=message, status_code=status_code, details=details)
