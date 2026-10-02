# Development Workflow

The development process always follows this order. Never skip phases.

## Phase 1: Discussion

- Explore ideas and clarify requirements with the user
- Evaluate technical trade-offs using the `architect` agent
- Do not write code until the approach is agreed upon

## Phase 2: Documentation

- Use the `planner` agent to break the agreed approach into steps
- Use the `doc-updater` agent to produce PRD, Design Doc, and ADRs
- Code must not start until documents are reviewed and approved

## Phase 3: Implementation (TDD)

1. Use the `tdd-guide` agent for all coding tasks
2. Write tests first (RED)
3. Implement minimally to pass tests (GREEN)
4. Refactor while keeping tests green (REFACTOR)
5. Verify 80%+ coverage before marking a task complete

## Phase 4: Review

- Use the `code-reviewer` agent after every meaningful change
- Use the `security-reviewer` agent when touching auth, APIs, or user input
- Address all CRITICAL and HIGH findings before merging

## Phase 5: Maintenance

- Use the `refactor-cleaner` agent for dead code removal
- Update documents in `docs/` when architecture changes
- Never run `refactor-cleaner` during active feature development
