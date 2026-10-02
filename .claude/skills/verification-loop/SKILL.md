---
name: verification-loop
description: Pre-PR quality gate. Run after completing a feature or significant change. Produces a structured PASS/FAIL report across build, types, lint, tests, security, and diff review.
---

# Verification Loop

Run this before creating any PR or marking a task complete. Work through each phase in order; stop and fix before continuing if a phase fails.

## Phase 0: ハーネス整合性チェック（ハーネスエンジニアリング適用済みプロジェクトのみ）

```bash
node .claude/hooks/structure-test.js
echo '{}' | node .claude/hooks/arch-lint.js 2>&1
```

エラーがあれば STOP。アプリケーションの検証に入る前に、ハーネス自体が正しく機能していることを確認する。

## コマンドの解決

Phase 1〜4 の各コマンドは `.claude/harness.json` の `commands` に定義があればそれを**優先して**使う。
以下の言語別コマンドは harness.json に定義がない場合のフォールバック例である。

```bash
node -pe "JSON.stringify(require('./.claude/harness.json').commands, null, 2)" 2>/dev/null
```

## Phase 1: Build

**TypeScript / Node.js**
```bash
npm run build 2>&1 | tail -20
```

**Python**
```bash
# If using a build step (e.g., packaging)
python -m build 2>&1 | tail -20
# Otherwise, a syntax check across all files
python -m compileall src/ 2>&1 | tail -20
```

If the build fails, STOP. Fix before continuing.

## Phase 2: Type Check

**TypeScript**
```bash
npx tsc --noEmit 2>&1 | head -30
```

**Python**
```bash
mypy src/ 2>&1 | head -30
# or
pyright . 2>&1 | head -30
```

Report all errors. Fix critical ones before continuing.

## Phase 3: Lint

**TypeScript / JavaScript**
```bash
npm run lint 2>&1 | head -30
```

**Python**
```bash
ruff check src/ 2>&1 | head -30
```

## Phase 4: Test Suite

**TypeScript**
```bash
npm test -- --coverage 2>&1 | tail -50
```

**Python**
```bash
pytest --cov=src --cov-report=term-missing 2>&1 | tail -50
```

Report:
- Total tests: X
- Passed: X / Failed: X
- Coverage: X% (target: 80%+)

If tests fail or coverage is below 80%, STOP.

## Phase 5: Security Scan

```bash
# Check for hardcoded secrets (adjust extensions as needed)
grep -rn "api_key\s*=\s*['\"]" --include="*.py" --include="*.ts" --include="*.js" src/ 2>/dev/null | head -10
grep -rn "sk-\|password\s*=\s*['\"]" --include="*.py" --include="*.ts" src/ 2>/dev/null | head -10

# Check for debug logging left in code
grep -rn "console\.log\|print(" --include="*.ts" --include="*.tsx" --include="*.py" src/ 2>/dev/null | head -10

# TypeScript: dependency audit
npm audit --audit-level=high

# Python: dependency audit
pip-audit 2>/dev/null || safety check 2>/dev/null
```

## Phase 6: Diff Review

```bash
git diff --stat
git diff HEAD --name-only
```

Review each changed file for:
- Unintended changes
- Missing error handling
- Potential edge cases not covered by tests

## Verification Report

After all phases, produce this report:

```
VERIFICATION REPORT
===================

Build:     PASS / FAIL
Types:     PASS / FAIL  (X errors)
Lint:      PASS / FAIL  (X warnings)
Tests:     PASS / FAIL  (X/Y passed, Z% coverage)
Security:  PASS / FAIL  (X issues)
Diff:      X files changed

Overall:   READY / NOT READY for PR

Issues to fix:
1. ...
2. ...
```

Only mark overall READY when all 6 phases pass.
