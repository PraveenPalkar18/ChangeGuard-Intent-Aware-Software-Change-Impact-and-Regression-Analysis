# ChangeGuard: Code Parsing Specification

## 1. Overview
The code parsing module is responsible for analyzing repository source files and extracting deterministic, structured representations of code entities (classes, functions, methods), imports, and function/method call sites. It uses **Tree-sitter** with the pinned `tree-sitter-python` grammar to produce robust abstract syntax trees (ASTs).

This module operates independently of GitHub APIs and AI models, providing a foundational substrate for downstream change-graph construction (M5), impact analysis (M6), and regression-test planning (M7).

---

## 2. Parser Abstraction
The parser architecture decouples language-specific AST walkers from consumers via the abstract base class:

```python
class BaseCodeParser(ABC):
    @abstractmethod
    def parse_source(self, file_path: str, source_code: str) -> ParseResult:
        """Parse source code into structured entities, imports, and calls."""
        pass

    @abstractmethod
    def supports_language(self, language: str) -> bool:
        """Determine if language or file extension is supported."""
        pass
```

The primary implementation is `TreeSitterPythonParser`, which accepts Python source code (`.py`) and returns a typed `ParseResult`. Unsupported languages (e.g. `.rs`, `.java`, `.go`) are explicitly rejected with `is_success=False` and a descriptive error message rather than silently reporting a success.

---

## 3. Extracted Entity Schema

### 3.1 CodeEntity
| Field | Type | Description |
| :--- | :--- | :--- |
| `id` | `str` | Deterministic identifier: `{file_path}::{enclosing_prefix}{name}` |
| `name` | `str` | Simple identifier name (e.g. `compute`) |
| `entity_type` | `CodeEntityType` | `CLASS`, `FUNCTION`, `METHOD`, or `MODULE` |
| `file_path` | `str` | Relative path from repository root |
| `start_line` | `int` | 1-indexed starting line (inclusive of decorators) |
| `end_line` | `int` | 1-indexed ending line |
| `parent_id` | `Optional[str]` | Enclosing class or function ID if nested |
| `docstring` | `Optional[str]` | Extracted docstring text |
| `parameters` | `List[str]` | Clean parameter names (excluding type hints/defaults) |
| `decorators` | `List[str]` | Applied decorators (e.g. `["@staticmethod"]`) |
| `is_async` | `bool` | True if asynchronous definition (`async def`) |

### 3.2 ImportEntity
Tracks dependency imports within the module:
- `module`: Target module (e.g. `os.path`, `math`, `..utils`)
- `name`: Specific symbol imported (e.g. `join`, or `None` for module-level imports)
- `alias`: Renamed symbol if using `as` (e.g. `pjoin`)
- `line_number`: 1-indexed source line
- `is_from_import`: True for `from x import y`, False for `import x`

### 3.3 CallSite
Captures function and method invocations for call graph tracing:
- `caller_entity_id`: ID of the enclosing function or method (or `None` for module-level calls)
- `callee_name`: Invoked symbol (e.g. `print`, `math.sqrt`, `self.validate`)
- `line_number`: 1-indexed invocation line
- `arguments_count`: Count of positional and keyword arguments passed

---

## 4. Concrete Example

### Input Source Code (`app/analytics.py`):
```python
import math
from typing import List

@timer
class DataProcessor:
    """Processes numerical data."""

    def __init__(self, precision: int = 2):
        self.precision = precision

    async def calculate_variance(self, values: List[float]) -> float:
        """Calculates variance of values."""
        avg = self._calculate_mean(values)
        total = 0.0
        for v in values:
            diff = v - avg
            total += math.pow(diff, 2)
        return total / len(values)

    def _calculate_mean(self, values: List[float]) -> float:
        return sum(values) / len(values)
```

### Extracted `ParseResult`:
```json
{
  "file_path": "app/analytics.py",
  "language": "python",
  "is_success": true,
  "has_syntax_errors": false,
  "raw_loc": 22,
  "entities": [
    {
      "id": "app/analytics.py::DataProcessor",
      "name": "DataProcessor",
      "entity_type": "class",
      "file_path": "app/analytics.py",
      "start_line": 4,
      "end_line": 22,
      "parent_id": null,
      "docstring": "Processes numerical data.",
      "parameters": [],
      "decorators": ["@timer"],
      "is_async": false
    },
    {
      "id": "app/analytics.py::DataProcessor.__init__",
      "name": "__init__",
      "entity_type": "method",
      "file_path": "app/analytics.py",
      "start_line": 8,
      "end_line": 9,
      "parent_id": "app/analytics.py::DataProcessor",
      "docstring": null,
      "parameters": ["self", "precision"],
      "decorators": [],
      "is_async": false
    },
    {
      "id": "app/analytics.py::DataProcessor.calculate_variance",
      "name": "calculate_variance",
      "entity_type": "method",
      "file_path": "app/analytics.py",
      "start_line": 11,
      "end_line": 19,
      "parent_id": "app/analytics.py::DataProcessor",
      "docstring": "Calculates variance of values.",
      "parameters": ["self", "values"],
      "decorators": [],
      "is_async": true
    },
    {
      "id": "app/analytics.py::DataProcessor._calculate_mean",
      "name": "_calculate_mean",
      "entity_type": "method",
      "file_path": "app/analytics.py",
      "start_line": 21,
      "end_line": 22,
      "parent_id": "app/analytics.py::DataProcessor",
      "docstring": null,
      "parameters": ["self", "values"],
      "decorators": [],
      "is_async": false
    }
  ],
  "imports": [
    {
      "module": "math",
      "name": null,
      "alias": null,
      "line_number": 1,
      "is_from_import": false
    },
    {
      "module": "typing",
      "name": "List",
      "alias": null,
      "line_number": 2,
      "is_from_import": true
    }
  ],
  "call_sites": [
    {
      "caller_entity_id": "app/analytics.py::DataProcessor.calculate_variance",
      "callee_name": "self._calculate_mean",
      "line_number": 13,
      "arguments_count": 1
    },
    {
      "caller_entity_id": "app/analytics.py::DataProcessor.calculate_variance",
      "callee_name": "math.pow",
      "line_number": 17,
      "arguments_count": 2
    },
    {
      "caller_entity_id": "app/analytics.py::DataProcessor.calculate_variance",
      "callee_name": "len",
      "line_number": 18,
      "arguments_count": 1
    },
    {
      "caller_entity_id": "app/analytics.py::DataProcessor._calculate_mean",
      "callee_name": "sum",
      "line_number": 22,
      "arguments_count": 1
    },
    {
      "caller_entity_id": "app/analytics.py::DataProcessor._calculate_mean",
      "callee_name": "len",
      "line_number": 22,
      "arguments_count": 1
    }
  ]
}
```

---

## 5. Association with Diff Hunks
The `EntityHunkMapper` bridges the gap between diff-hunk line modifications and parsed AST entities:
1. **Added Lines (`+`)**: Evaluated against the **new source code AST**. If lines fall inside `[start_line, end_line]`, the innermost entity (e.g. method over class) is assigned with association type `enclosing`.
2. **Modified Lines**: When additions and deletions occur in the same hunk, line numbers in the new file are mapped to the new AST.
3. **Deleted Lines (`-`)**: Evaluated against the **old source code AST** (if provided). A deleted function is explicitly associated with its old AST definition without falsely claiming it exists in the new source.
4. **File-Level Modifications**: Top-level statements (e.g. module constants, imports) outside any class or function are classified as `file_level` with `matched_entity_id = None`.

---

## 6. Syntax Error Handling & Resilience
- **Error Nodes**: Tree-sitter embeds `ERROR` and `MISSING` nodes inside syntax trees without crashing.
- **Partial Recovery**: All valid surrounding classes, functions, calls, and imports are preserved.
- **Diagnostic Logging**: Each error node records start/end line numbers and error snippet in `error_nodes`.

---

## 7. Known Limitations
1. **Dynamic Call Resolution**: Static parsing records invocations as text (e.g. `self.calculate()`). Calls via `getattr()`, `*args` unpacking, or runtime reflection cannot be statically resolved without symbolic execution.
2. **Multi-Language Support**: Currently limited to Python; additional language grammars (JavaScript/TypeScript, Go, Java) will require implementing `BaseCodeParser` subclasses in future iterations.
