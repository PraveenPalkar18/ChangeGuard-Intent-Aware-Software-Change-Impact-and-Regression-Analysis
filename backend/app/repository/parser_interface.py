"""Abstract code parser interface for extensible language support."""
from abc import ABC, abstractmethod
from backend.app.repository.models import ParseResult


class BaseCodeParser(ABC):
    """Abstract base class defining the contract for source code parsers."""

    @abstractmethod
    def parse_source(self, file_path: str, source_code: str) -> ParseResult:
        """Parse the given source code and extract code entities, imports, and calls.

        Args:
            file_path: Path to the file relative to repository root.
            source_code: Raw source code string.

        Returns:
            ParseResult containing entities, imports, calls, syntax errors, and status.
        """
        pass

    @abstractmethod
    def supports_language(self, language: str) -> bool:
        """Determine if this parser supports the specified programming language.

        Args:
            language: Language name or extension (e.g. 'python', 'py').

        Returns:
            True if supported, False otherwise.
        """
        pass
