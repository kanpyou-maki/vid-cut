---
paths:
  - "**/*.py"
  - "**/*.pyi"
---
# Python Security

> Extends common/security.md with Python specifics.

## Secret Management

```python
import os
from dotenv import load_dotenv

load_dotenv()

# Raises KeyError at startup if the variable is missing — fail fast
api_key = os.environ["API_KEY"]
```

## SQL Injection Prevention

```python
# WRONG: String formatting
cursor.execute(f"SELECT * FROM users WHERE id = {user_id}")

# CORRECT: Parameterized query
cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
```

## Input Validation

Use Pydantic for schema-based validation at system boundaries:

```python
from pydantic import BaseModel, EmailStr

class CreateUserRequest(BaseModel):
    name: str
    email: EmailStr
    age: int

request = CreateUserRequest(**raw_input)  # raises ValidationError if invalid
```

## Static Security Analysis

Run before every release:

```bash
bandit -r src/
```
