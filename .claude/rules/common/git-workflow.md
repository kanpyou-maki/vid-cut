# Git Workflow

## Commit Message Format

```
<type>: <description>

<optional body>
```

Types: `feat`, `fix`, `refactor`, `docs`, `test`, `chore`, `perf`, `ci`

Examples:
```
feat: add user authentication endpoint
fix: handle null response from payment API
test: add unit tests for calculateTotal
chore: remove unused dependencies
```

## Pull Request Workflow

When creating PRs:
1. Analyze full commit history since the branch diverged (`git diff [base]...HEAD`)
2. Write a clear summary of what changed and why
3. Include a test plan checklist
4. Push with `-u` flag if the branch is new

## Branch Naming

```
feat/short-description
fix/issue-description
chore/task-description
```
