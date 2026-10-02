---
paths:
  - "**/*.py"
  - "**/*.pyi"
---
# Python Testing

> Extends common/testing.md with Python specifics.

## Framework

Use **pytest** as the testing framework.

## Coverage Command

```bash
pytest --cov=src --cov-report=term-missing
```

Minimum 80% coverage required before a task is complete.

## Test Organization

Co-locate tests with implementation, or use a top-level `tests/` directory:

```
src/
├── feature/
│   ├── service.py
│   └── test_service.py
```

Use `pytest.mark` to categorize tests:

```python
import pytest

@pytest.mark.unit
def test_calculate_total():
    ...

@pytest.mark.integration
def test_database_connection():
    ...
```

## Fixtures for Dependencies

```python
import pytest

@pytest.fixture
def user_repository():
    return FakeUserRepository()

def test_get_user_returns_correct_data(user_repository):
    result = get_user("123", repo=user_repository)
    assert result["id"] == "123"
```

## Mocking External Dependencies

```python
from unittest.mock import patch, MagicMock

def test_sends_email_on_registration():
    with patch("src.services.email.send") as mock_send:
        register_user(email="user@example.com")
        mock_send.assert_called_once()
```
