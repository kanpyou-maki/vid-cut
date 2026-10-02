---
paths:
  - "**/*.ts"
  - "**/*.tsx"
  - "**/*.js"
  - "**/*.jsx"
---
# TypeScript/JavaScript Security

> Extends common/security.md with TypeScript/JavaScript specifics.

## Secret Management

```typescript
// NEVER: Hardcoded secrets
const apiKey = "sk-proj-xxxxx"

// ALWAYS: Environment variables with startup validation
const apiKey = process.env.API_KEY
if (!apiKey) throw new Error('API_KEY is not configured')
```

## SQL Injection Prevention

```typescript
// WRONG: String concatenation
const q = `SELECT * FROM users WHERE id = '${userId}'`

// CORRECT: Parameterized query
const q = `SELECT * FROM users WHERE id = $1`
await db.query(q, [userId])
```

## XSS Prevention

```typescript
// WRONG: Raw HTML from user input
element.innerHTML = userInput

// CORRECT: Text content or sanitized HTML
element.textContent = userInput
// or
element.innerHTML = DOMPurify.sanitize(userInput)
```

## Dependency Auditing

Run before every release:
```bash
npm audit --audit-level=high
```
