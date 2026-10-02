# Common Patterns

## Repository Pattern

Encapsulate data access behind a consistent interface:
- Define standard operations: findAll, findById, create, update, delete
- Concrete implementations handle storage details (database, API, cache, etc.)
- Business logic depends on the abstract interface, not the storage mechanism
- Enables easy swapping of data sources and simplifies testing with mocks

## API Response Format

Use a consistent envelope for all API responses:

```
{
  success: boolean,
  data?: T,            // payload (null on error)
  error?: string,      // error message (null on success)
  meta?: {             // pagination metadata when applicable
    total, page, limit
  }
}
```

## Service Layer

Separate business logic from data access and transport:
- Controllers / route handlers handle HTTP concerns only
- Service layer contains business logic
- Repository layer handles persistence
- Keep each layer independently testable

## Dependency Injection

Pass dependencies as constructor arguments or function parameters rather than importing them directly. This makes components testable in isolation without side effects.
