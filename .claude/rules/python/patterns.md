---
paths:
  - "**/*.py"
  - "**/*.pyi"
---
# Python Patterns

> Extends common/patterns.md with Python specifics.

## Repository Pattern (Protocol)

Use `Protocol` for duck-typed interfaces:

```python
from typing import Protocol

class UserRepository(Protocol):
    def find_by_id(self, id: str) -> dict | None: ...
    def save(self, entity: dict) -> dict: ...
    def delete(self, id: str) -> None: ...
```

## Dataclasses as DTOs

```python
from dataclasses import dataclass

@dataclass
class CreateUserRequest:
    name: str
    email: str
    age: int | None = None
```

## Context Managers for Resource Handling

Always use `with` for resources that need cleanup:

```python
# CORRECT
with open('file.txt') as f:
    content = f.read()

# CORRECT
async with httpx.AsyncClient() as client:
    response = await client.get(url)
```

## Dependency Injection

Pass dependencies explicitly rather than importing globals:

```python
# WRONG: hidden dependency
def get_user(user_id: str) -> dict:
    return db.query(...)  # module-level db

# CORRECT: explicit dependency
def get_user(user_id: str, *, repo: UserRepository) -> dict:
    return repo.find_by_id(user_id)
```
