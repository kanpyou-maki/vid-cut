#!/usr/bin/env node
/**
 * Git Push Reminder Hook (PreToolUse: Bash)
 *
 * Displays a reminder message before `git push` commands.
 * Does not block the push — informational only.
 *
 * No external dependencies — copy to .claude/hooks/ and reference from settings.json.
 */

'use strict';

const MAX_STDIN = 1024 * 1024;
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
      console.error('[Hook] git push を実行します。変更内容を確認しましたか？');
      console.error('[Hook] verification-loop を未実行の場合は .claude/skills/verification-loop/SKILL.md を参照してください。');
    }
  } catch {
    // Ignore parse errors — pass through
  }

  process.stdout.write(raw);
});
