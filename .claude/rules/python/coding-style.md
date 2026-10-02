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

- **black** — code formatting (`black src/`)
- **isort** — import sorting (`isort src/`)
- **ruff** — linting (`ruff check src/`)

Run all three before committing.

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
