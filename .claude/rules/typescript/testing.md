---
paths:
  - "**/*.ts"
  - "**/*.tsx"
  - "**/*.js"
  - "**/*.jsx"
---
# TypeScript/JavaScript Testing

> Extends common/testing.md with TypeScript/JavaScript specifics.

## Frameworks

- **Unit / Integration**: Jest or Vitest
- **E2E**: Playwright

## Coverage Command

```bash
# Jest
npx jest --coverage

# Vitest
npx vitest run --coverage
```

## Test File Naming

Co-locate tests with implementation:

```
src/
├── feature/
│   ├── feature.ts
│   └── feature.test.ts
└── e2e/
    └── critical-flow.spec.ts
```

## Mocking External Dependencies

```typescript
// Mock a module
jest.mock('@/lib/database', () => ({
  db: {
    query: jest.fn().mockResolvedValue({ rows: [] }),
  },
}))

// Mock in Vitest
vi.mock('@/lib/database', () => ({ ... }))
```

## React Component Testing

```typescript
import { render, screen } from '@testing-library/react'

it('shows error message when input is invalid', () => {
  render(<Form />)
  fireEvent.click(screen.getByRole('button', { name: 'Submit' }))
  expect(screen.getByRole('alert')).toHaveTextContent('Required')
})
```
