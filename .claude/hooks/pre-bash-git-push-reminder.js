#!/usr/bin/env node
/**
 * Git Push Reminder Hook (PreToolUse: Bash)
 *
 * Hands the model a reminder before `git push` commands.
 * Does not block the push — informational only.
 *
 * The reminder is returned as `additionalContext` JSON on stdout: on exit 0, plain stdout/stderr
 * never reaches the model (ADR-005). settings.json limits this hook to `git push` with the `if` field.
 *
 * No external dependencies — copy to .claude/hooks/ and reference from settings.json.
 */

'use strict';

const MAX_STDIN = 1024 * 1024;
const REMINDER = 'git push の前に: review-loop（.claude/skills/review-loop/SKILL.md）を未実行なら、先に通過させてください。';
let raw = '';

process.stdin.setEncoding('utf8');
process.stdin.on('data', chunk => {
  if (raw.length < MAX_STDIN) {
    raw += chunk.substring(0, MAX_STDIN - raw.length);
  }
});

process.stdin.on('end', () => {
  try {
    const input = JSON.parse(raw);
    const cmd = String(input.tool_input?.command || '');

    if (/\bgit\s+push\b/.test(cmd)) {
      process.stdout.write(JSON.stringify({
        hookSpecificOutput: { hookEventName: 'PreToolUse', additionalContext: REMINDER },
      }));
    }
  } catch {
    // Ignore parse errors — nothing to remind
  }
});
