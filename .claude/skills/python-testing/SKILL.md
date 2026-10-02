---
name: python-testing
description: Pytest patterns for TDD in Python. Covers fixtures, parametrize, mocking, async testing, conftest, and test organization. Reference when writing or reviewing Python tests.
---

# Python Testing Patterns (pytest)

## Setup

```bash
pip install pytest pytest-cov pytest-asyncio
pytest --cov=src --cov-report=term-missing
```

```toml
# pyproject.toml
[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = ["--strict-markers", "--cov=src", "--cov-report=term-missing"]
markers = [
    "unit: unit tests",
    "integration: integration tests",
    "slow: slow tests",
]
```

## Test Structure

```python
# tests/unit/test_user_service.py

def test_create_user_returns_user_with_id():
    service = UserService()
    user = service.create("Alice", "alice@example.com")
    assert user.id is not None
    assert user.name == "Alice"

def test_create_user_raises_on_invalid_email():
    service = UserService()
    with pytest.raises(ValidationError, match="invalid email"):
        service.create("Alice", "not-an-email")
```

## Fixtures

### Basic Fixture

```python
@pytest.fixture
def user_repo():
    return FakeUserRepository()

def test_get_user(user_repo):
    user_repo.save(User(id="1", name="Alice"))
    result = user_repo.find_by_id("1")
    assert result.name == "Alice"
```

### Fixture with Setup / Teardown

```python
@pytest.fixture
def db():
    conn = Database(":memory:")
    conn.create_tables()
    yield conn
    conn.close()
```

### Fixture Scopes

```python
@pytest.fixture(scope="function")  # default — fresh per test
@pytest.fixture(scope="module")    # once per file
@pytest.fixture(scope="session")   # once per test run
```

### conftest.py — Shared Fixtures

```python
# tests/conftest.py
import pytest

@pytest.fixture
def client():
    app = create_app(testing=True)
    with app.test_client() as client:
        yield client

@pytest.fixture
def auth_headers(client):
    resp = client.post("/api/login", json={"username": "test", "password": "test"})
    token = resp.json["token"]
    return {"Authorization": f"Bearer {token}"}
```

### Autouse Fixture

```python
@pytest.fixture(autouse=True)
def reset_database():
    """Runs before every test automatically."""
    Database.reset()
    yield
    Database.cleanup()
```

## Parametrize

```python
@pytest.mark.parametrize("email,valid", [
    ("user@example.com", True),
    ("not-an-email",     False),
    ("@missing.com",     False),
], ids=["valid", "missing-at", "missing-domain"])
def test_email_validation(email, valid):
    assert is_valid_email(email) is valid

@pytest.mark.parametrize("a,b,expected", [
    (2, 3, 5),
    (0, 0, 0),
    (-1, 1, 0),
])
def test_add(a, b, expected):
    assert add(a, b) == expected
```

## Mocking

### Patch a Function

```python
from unittest.mock import patch, Mock

@patch("mypackage.services.send_email")
def test_sends_email_on_registration(mock_send):
    register_user(email="user@example.com")
    mock_send.assert_called_once()
```

### Patch Return Value

```python
@patch("mypackage.repos.UserRepository.find_by_id")
def test_get_user(mock_find):
    mock_find.return_value = User(id="1", name="Alice")
    result = get_user("1")
    assert result.name == "Alice"
```

### Patch Side Effect (Exception)

```python
@patch("mypackage.api.http_get")
def test_handles_network_error(mock_get):
    mock_get.side_effect = ConnectionError("timeout")
    with pytest.raises(ServiceUnavailableError):
        fetch_data()
```

### Mock File I/O

```python
from unittest.mock import patch, mock_open

@patch("builtins.open", mock_open(read_data="file content"))
def test_reads_file():
    result = read_file("config.txt")
    assert result == "file content"
```

### Autospec — Catch Interface Misuse

```python
@patch("mypackage.UserRepository", autospec=True)
def test_calls_correct_method(mock_repo):
    service = UserService(mock_repo.return_value)
    service.get_user("123")
    mock_repo.return_value.find_by_id.assert_called_once_with("123")
```

## Async Testing

```python
# pip install pytest-asyncio

@pytest.mark.asyncio
async def test_async_fetch():
    result = await fetch_data("http://example.com")
    assert result["status"] == "ok"

@pytest.fixture
async def async_client():
    app = create_app()
    async with app.test_client() as client:
        yield client

@pytest.mark.asyncio
async def test_async_endpoint(async_client):
    resp = await async_client.get("/api/users")
    assert resp.status == 200
```

### Mocking Async Functions

```python
@pytest.mark.asyncio
@patch("mypackage.async_api_call")
async def test_async_mock(mock_call):
    mock_call.return_value = {"ok": True}
    result = await my_async_function()
    mock_call.assert_awaited_once()
    assert result["ok"] is True
```

## Testing API Endpoints (FastAPI / Flask)

```python
# FastAPI
from fastapi.testclient import TestClient

@pytest.fixture
def client():
    return TestClient(app)

def test_get_users(client):
    resp = client.get("/api/users")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)

def test_create_user(client, auth_headers):
    resp = client.post("/api/users",
        json={"name": "Alice", "email": "alice@example.com"},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    assert resp.json()["name"] == "Alice"
```

## Testing Database Operations

```python
@pytest.fixture
def db_session():
    session = Session(bind=engine)
    session.begin_nested()   # savepoint
    yield session
    session.rollback()       # rollback to savepoint — no data persists
    session.close()

def test_create_user(db_session):
    user = User(name="Alice", email="alice@example.com")
    db_session.add(user)
    db_session.flush()
    assert user.id is not None
```

## Test Organization

```
tests/
├── conftest.py              # Shared fixtures
├── unit/
│   ├── test_models.py
│   ├── test_services.py
│   └── test_utils.py
├── integration/
│   ├── test_api.py
│   └── test_database.py
└── e2e/
    └── test_user_flow.py
```

## Running Tests

```bash
pytest                              # All tests
pytest tests/unit/                  # Unit only
pytest -m "not slow"                # Skip slow tests
pytest -k "test_user"               # Tests matching pattern
pytest -x                           # Stop on first failure
pytest --lf                         # Last failed only
pytest -v                           # Verbose output
pytest --pdb                        # Drop into debugger on failure
```

## Best Practices

**DO:**
- Write tests before code (TDD: red → green → refactor)
- One behavior per test
- Descriptive names: `test_create_user_raises_on_duplicate_email`
- Use fixtures to eliminate setup duplication
- Mock external dependencies (DB, HTTP, file system) in unit tests
- Test edge cases: None, empty, boundary values

**DON'T:**
- Test implementation internals — test observable behavior
- Share mutable state between tests
- Catch exceptions inside tests — use `pytest.raises`
- Leave `print()` in test code
- Write tests that only pass in a specific order
