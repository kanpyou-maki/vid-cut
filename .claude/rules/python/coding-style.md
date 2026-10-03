---
paths:
  - "**/*.py"
  - "**/*.pyi"
---
# Python Coding Style

> Extends common/coding-style.md with Python specifics.

## Standards

- Follow **PEP 8** conventions
- Use **type annotations** on all function signatures

## Immutability

Prefer immutable data structures:

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class User:
    name: str
    email: str

from typing import NamedTuple

class Point(NamedTuple):
    x: float
    y: float
```

## Formatting Tools

Use the formatter and linter this project has chosen. Do not assume a specific tool.

- The source of truth is `commands.lint` in `.claude/harness.json`. It runs the lint and the format check. Run it before committing.
- Typical setups: `ruff format` + `ruff check` (its `I` rules check import order), or `black` + `isort` + `ruff check`.
- Formatting is judged by the result of that command, not by which tool the project uses.

## Error Handling

Use specific exception types; never use bare `except`:

```python
# WRONG
try:
    result = risky_operation()
except:
    pass

# CORRECT
try:
    result = risky_operation()
except ValueError as e:
    logger.error("Validation failed: %s", e)
    raise
```
