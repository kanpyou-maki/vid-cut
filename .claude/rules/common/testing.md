# Testing Requirements

## Minimum Coverage: 80%

All three test types are required:

1. **Unit tests** — Individual functions, utilities, components in isolation
2. **Integration tests** — API endpoints, database operations, service interactions
3. **E2E tests** — Critical user flows (framework chosen per language/stack)

## TDD Workflow (MANDATORY)

1. Write the test first (RED)
2. Run it — it must FAIL
3. Write the minimal implementation (GREEN)
4. Run it — it must PASS
5. Refactor while keeping tests green
6. Verify coverage is 80%+

Never write implementation code before a failing test exists.

## Test Quality Rules

- Tests must be independent — no shared mutable state between tests
- Each test asserts one behavior
- Mock external dependencies (DB, APIs, file system) in unit tests
- Test error paths, not only happy paths
- Test edge cases: null, empty, boundary values, invalid input

## Coverage Requirements by Category

| Code Type | Minimum Coverage |
|-----------|-----------------|
| General | 80% |
| Financial calculations | 100% |
| Authentication logic | 100% |
| Security-critical paths | 100% |

## Troubleshooting Failing Tests

1. Use the `tdd-guide` agent
2. Check test isolation (shared state leaking between tests?)
3. Verify mocks match the actual interface
4. Fix the implementation, not the test — unless the test itself is wrong
