# ChangeGuard: Code Parsing Specification

## 1. Overview
The code parsing module is responsible for analyzing repository source files and extracting deterministic, structured representations of code entities (classes, functions, methods), imports, and call sites.

ChangeGuard employs **Universal Multi-Language AST Parsing** via `UniversalCodeParser` (`backend/app/repository/universal_parser.py`):
1. **High-Precision Native Tree-sitter Grammars**: Pinned Tree-sitter parsers for Python, JavaScript, TypeScript, Go, Java, Rust, and C#.
2. **Universal Heuristic Regex Fallback**: A resilient syntactic extractor for all other languages (e.g. Ruby, PHP, Kotlin, Swift, Dart, Scala, C/C++, Shell).
3. **Binary/Media File Filtering**: Ignores lockfiles, source maps, bundled minified assets, and binary/media files (`.png`, `.lock`, `.min.js`, etc.).

This module operates independently of GitHub APIs and AI models, providing a foundational substrate for downstream change-graph construction, impact analysis, and regression-test planning.

---

## 2. Universal Parser Architecture

The parser implements the abstract base contract `BaseCodeParser`:

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

### 2.1 Supported Languages & Parsers

| Language | Extensions | Parser Engine | Extracted Constructs |
| :--- | :--- | :--- | :--- |
| **Python** | `.py`, `.pyw`, `.pyi` | Tree-sitter (`tree-sitter-python`) | Classes, functions, methods, decorators, async, docstrings, imports, call sites |
| **JavaScript** | `.js`, `.jsx`, `.mjs`, `.cjs` | Tree-sitter (`tree-sitter-javascript`) | Classes, functions, methods, arrow functions, ES modules, `require`, calls |
| **TypeScript** | `.ts`, `.tsx` | Tree-sitter (`tree-sitter-typescript`) | Interfaces, classes, methods, arrow functions, types, imports, calls |
| **Go** | `.go` | Tree-sitter (`tree-sitter-go`) | Packages, structs, interfaces, functions, methods with receivers, imports, calls |
| **Java** | `.java` | Tree-sitter (`tree-sitter-java`) | Packages, classes, interfaces, methods, constructors, imports, method calls |
| **Rust** | `.rs` | Tree-sitter (`tree-sitter-rust`) | Structs, traits, enums, functions, `impl` methods, `use` statements, calls |
| **C#** | `.cs` | Tree-sitter (`tree-sitter-c-sharp`) | Namespaces, classes, interfaces, methods, properties, `using` imports, calls |
| **Generic Fallback** | `.rb`, `.php`, `.kt`, `.swift`, `.c`, `.cpp`, `.scala`, `.dart`, `.sh` | Syntactic Regex Heuristic | Functions, methods, classes, modules, calls, imports |

---

## 3. Extracted Entity Schema

### 3.1 `CodeEntity`
| Field | Type | Description |
| :--- | :--- | :--- |
| `id` | `str` | Deterministic identifier: `{file_path}::{enclosing_prefix}{name}` |
| `name` | `str` | Simple identifier name (e.g. `calculate_tax` or `UserAuthService`) |
| `entity_type` | `CodeEntityType` | `CLASS`, `FUNCTION`, `METHOD`, `INTERFACE`, `STRUCT`, or `MODULE` |
| `file_path` | `str` | Relative path from repository root (e.g. `src/auth/service.ts`) |
| `start_line` | `int` | 1-indexed starting line (inclusive of decorators/attributes) |
| `end_line` | `int` | 1-indexed ending line |
| `parent_id` | `Optional[str]` | Enclosing class, struct, or namespace ID if nested |
| `docstring` | `Optional[str]` | Extracted docstring or leading comment block |
| `parameters` | `List[str]` | Parameter names |
| `decorators` | `List[str]` | Applied decorators/annotations (e.g. `["@injectable"]`, `["@Override"]`) |
| `is_async` | `bool` | True if asynchronous definition (`async def`, `async () =>`, etc.) |

### 3.2 `ImportEntity`
Tracks dependency imports within the module:
- `module`: Target module (e.g. `react`, `express`, `fmt`, `os.path`)
- `name`: Specific symbol imported (e.g. `useState`, `Router`, or `None` for package-level imports)
- `alias`: Renamed symbol if aliased (e.g. `import * as React from 'react'`)
- `line_number`: 1-indexed source line
- `is_from_import`: True for explicit member imports (`from x import y`, `import { y } from 'x'`)

### 3.3 `CallSite`
Captures invocations for call graph tracing:
- `caller_entity_id`: ID of the enclosing entity (or `None` for module-level calls)
- `callee_name`: Invoked symbol (e.g. `db.query`, `self.validate`, `fmt.Println`)
- `line_number`: 1-indexed invocation line
- `arguments_count`: Count of arguments passed

---

## 4. Concrete Multi-Language Examples

### 4.1 TypeScript Example (`src/services/billing.ts`)
```typescript
import { StripeClient } from '../clients/stripe';

export class BillingService {
    private client: StripeClient;

    constructor() {
        this.client = new StripeClient();
    }

    public async processPayment(userId: string, amount: number): Promise<boolean> {
        const validated = this.validateUser(userId);
        if (!validated) return false;
        return await this.client.charge(userId, amount);
    }

    private validateUser(userId: string): boolean {
        return userId.length > 0;
    }
}
```

**Parsed Result**:
- Entity: `src/services/billing.ts::BillingService` (CLASS, lines 3-18)
- Entity: `src/services/billing.ts::BillingService.processPayment` (METHOD, lines 10-14, async)
- Entity: `src/services/billing.ts::BillingService.validateUser` (METHOD, lines 16-18)
- Call: `BillingService.processPayment` $\rightarrow$ `this.validateUser` (line 11)
- Call: `BillingService.processPayment` $\rightarrow$ `this.client.charge` (line 13)
- Import: `../clients/stripe` importing `StripeClient` (line 1)

### 4.2 Go Example (`pkg/auth/token.go`)
```go
package auth

import "time"

type TokenManager struct {
    secret string
}

func (tm *TokenManager) ValidateToken(token string) bool {
    if len(token) == 0 {
        return false
    }
    return tm.checkExpiry(token)
}

func (tm *TokenManager) checkExpiry(token string) bool {
    return time.Now().Unix() > 0
}
```

**Parsed Result**:
- Entity: `pkg/auth/token.go::TokenManager` (STRUCT, lines 5-7)
- Entity: `pkg/auth/token.go::TokenManager.ValidateToken` (METHOD, lines 9-14)
- Entity: `pkg/auth/token.go::TokenManager.checkExpiry` (METHOD, lines 16-18)
- Call: `TokenManager.ValidateToken` $\rightarrow$ `tm.checkExpiry` (line 13)
- Import: `time` (line 3)

---

## 5. Entity-Hunk Association (`EntityHunkMapper`)

`EntityHunkMapper` bridges git diff hunks with the parsed AST:
1. **Added/Modified Lines**: Mapped against the **New** (HEAD) revision AST.
2. **Deleted Lines**: Mapped against the **Old** (BASE) revision AST. This ensures deleted functions or classes are identified without erroneously asserting they still exist in the new codebase.
3. **Association Tiers**:
   - `ENCLOSING`: The modified lines reside entirely within the start and end boundaries of a function, method, or class.
   - `OVERLAPPING`: The hunk crosses the signature or boundaries of an entity (e.g. changing parameters or renaming).
   - `FILE_LEVEL`: The hunk changes top-level constants, global statements, or imports outside any function/class.

---

## 6. Syntax Error Tolerance & Recovery

In real PRs, source code may be in an intermediate, incomplete, or syntactically invalid state:
- Tree-sitter constructs a concrete syntax tree resiliently by isolating `ERROR` nodes.
- `UniversalCodeParser` logs syntax errors as `ParseErrorNode` records but continues parsing all surrounding valid classes, functions, and methods.
- The pipeline never crashes or returns an empty result due to localized syntax errors.
