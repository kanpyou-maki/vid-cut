---
name: python-patterns
description: Pythonic idioms, type hints, error handling, context managers, concurrency, and package organization. Reference when writing or reviewing Python code.
---

# Python Development Patterns

## Core Principles

### Readability Counts

```python
# GOOD: Clear and readable
def get_active_users(users: list[User]) -> list[User]:
    return [user for user in users if user.is_active]

# BAD: Clever but opaque
def get_active_users(u):
    return [x for x in u if x.a]
```

### EAFP — Easier to Ask Forgiveness Than Permission

Python prefers exception handling over pre-condition checks:

```python
# GOOD: EAFP
try:
    return dictionary[key]
except KeyError:
    return default_value

# LESS PYTHONIC: LBYL
if key in dictionary:
    return dictionary[key]
return default_value
```

## Type Hints

### Modern Annotations (Python 3.9+)

```python
def process_items(items: list[str]) -> dict[str, int]:
    return {item: len(item) for item in items}

def first(items: list[T]) -> T | None:
    return items[0] if items else None
```

### Protocol — Duck Typing Interfaces

```python
from typing import Protocol

class Repository(Protocol):
    def find_by_id(self, id: str) -> dict | None: ...
    def save(self, entity: dict) -> dict: ...
```

### Type Aliases

```python
from typing import Any, Union
JSON = Union[dict[str, Any], list[Any], str, int, float, bool, None]
```

## Error Handling

### Specific Exception Types

```python
# GOOD: Catch specific exceptions, chain context
def load_config(path: str) -> Config:
    try:
        with open(path) as f:
            return Config.from_json(f.read())
    except FileNotFoundError as e:
        raise ConfigError(f"Config file not found: {path}") from e
    except json.JSONDecodeError as e:
        raise ConfigError(f"Invalid JSON in config: {path}") from e

# BAD: Silent failure with bare except
try:
    ...
except:
    return None
```

### Custom Exception Hierarchy

```python
class AppError(Exception):
    """Base exception for all application errors."""

class ValidationError(AppError):
    """Raised when input validation fails."""

class NotFoundError(AppError):
    """Raised when a requested resource is not found."""
```

## Data Classes and Named Tuples

### Dataclasses

```python
from dataclasses import dataclass, field
from datetime import datetime

@dataclass
class User:
    id: str
    name: str
    email: str
    created_at: datetime = field(default_factory=datetime.now)
    is_active: bool = True

@dataclass
class CreateUserRequest:
    name: str
    email: str
    age: int | None = None

    def __post_init__(self):
        if "@" not in self.email:
            raise ValueError(f"Invalid email: {self.email}")
```

### Frozen Dataclass (Immutable)

```python
@dataclass(frozen=True)
class Point:
    x: float
    y: float
```

### Named Tuple

```python
from typing import NamedTuple

class Point(NamedTuple):
    x: float
    y: float

    def distance(self, other: 'Point') -> float:
        return ((self.x - other.x) ** 2 + (self.y - other.y) ** 2) ** 0.5
```

## Context Managers

```python
# Always use `with` for resources
with open(path) as f:
    content = f.read()

# Custom context manager
from contextlib import contextmanager

@contextmanager
def timer(name: str):
    start = time.perf_counter()
    yield
    elapsed = time.perf_counter() - start
    print(f"{name}: {elapsed:.4f}s")

# Class-based with transaction semantics
class DatabaseTransaction:
    def __enter__(self):
        self.connection.begin()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is None:
            self.connection.commit()
        else:
            self.connection.rollback()
        return False  # Do not suppress exceptions
```

## Generators and Comprehensions

```python
# List comprehension for simple transformations
names = [user.name for user in users if user.is_active]

# Generator for lazy evaluation (memory-efficient)
total = sum(x * x for x in range(1_000_000))

# Generator function for large files
def read_lines(path: str) -> Iterator[str]:
    with open(path) as f:
        for line in f:
            yield line.strip()
```

## Concurrency

### I/O-Bound — asyncio

```python
import asyncio
import aiohttp

async def fetch(url: str) -> str:
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            return await response.text()

async def fetch_all(urls: list[str]) -> list[str]:
    tasks = [fetch(url) for url in urls]
    return await asyncio.gather(*tasks, return_exceptions=True)
```

### I/O-Bound — ThreadPoolExecutor

```python
import concurrent.futures

def fetch_all_sync(urls: list[str]) -> dict[str, str]:
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(fetch_sync, url): url for url in urls}
        return {futures[f]: f.result() for f in concurrent.futures.as_completed(futures)}
```

### CPU-Bound — ProcessPoolExecutor

```python
with concurrent.futures.ProcessPoolExecutor() as executor:
    results = list(executor.map(heavy_computation, datasets))
```

## Package Organization

```
myproject/
├── src/
│   └── mypackage/
│       ├── __init__.py        # Export public API
│       ├── api/
│       │   └── routes.py
│       ├── models/
│       │   └── user.py
│       └── utils/
│           └── helpers.py
├── tests/
│   ├── conftest.py
│   ├── unit/
│   └── integration/
├── pyproject.toml
└── .gitignore
```

### pyproject.toml

```toml
[project]
name = "mypackage"
version = "1.0.0"
requires-python = ">=3.9"
dependencies = ["pydantic>=2.0.0"]

[project.optional-dependencies]
dev = ["pytest>=7.4.0", "pytest-cov", "black", "ruff", "mypy"]

[tool.black]
line-length = 88

[tool.ruff]
line-length = 88
select = ["E", "F", "I", "N", "W"]

[tool.mypy]
python_version = "3.9"
disallow_untyped_defs = true
warn_return_any = true

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "--cov=mypackage --cov-report=term-missing"
```

## Anti-Patterns to Avoid

```python
# BAD: Mutable default argument — shared across all calls
def append_to(item, items=[]):
    items.append(item)
    return items

# GOOD:
def append_to(item, items=None):
    if items is None:
        items = []
    items.append(item)
    return items

# BAD: type() instead of isinstance()
if type(obj) == list: ...

# GOOD:
if isinstance(obj, list): ...

# BAD: Comparing to None with ==
if value == None: ...

# GOOD:
if value is None: ...

# BAD: Star import
from os.path import *

# GOOD: Explicit import
from os.path import join, exists

# BAD: String concatenation in loops — O(n²)
result = ""
for item in items:
    result += str(item)

# GOOD: join — O(n)
result = "".join(str(item) for item in items)
```

## Tooling Quick Reference

```bash
black .          # Format
isort .          # Sort imports
ruff check .     # Lint
mypy .           # Type check
bandit -r src/   # Security scan
pytest --cov=src # Tests + coverage
```
