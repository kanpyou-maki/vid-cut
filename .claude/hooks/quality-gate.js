#!/usr/bin/env node
/**
 * Quality Gate Hook (PostToolUse: Edit | Write | MultiEdit)
 *
 * Runs lightweight format/lint checks after file edits.
 * - TypeScript/JS: Biome (if biome.json exists) → Prettier fallback
 * - Python: ruff format + ruff check
 *
 * No external dependencies — copy to .claude/hooks/ and reference from settings.json.
 */

'use strict';

const fs = require('fs');
const path = require('path');
const { spawnSync } = require('child_process');

const MAX_STDIN = 1024 * 1024;
let raw = '';

function run(command, args, cwd = process.cwd()) {
  return spawnSync(command, args, {
    cwd,
    encoding: 'utf8',
    env: process.env,
  });
}

function maybeRunQualityGate(filePath) {
  if (!filePath || !fs.existsSync(filePath)) {
    return;
  }

  const ext = path.extname(filePath).toLowerCase();
  const cwd = process.cwd();

  if (['.ts', '.tsx', '.js', '.jsx', '.json', '.md'].includes(ext)) {
    const hasBiome =
      fs.existsSync(path.join(cwd, 'biome.json')) ||
      fs.existsSync(path.join(cwd, 'biome.jsonc'));

    if (hasBiome) {
      run('npx', ['biome', 'check', '--write', filePath]);
    } else {
      run('npx', ['prettier', '--write', filePath]);
    }
    return;
  }

  if (ext === '.py') {
    run('ruff', ['format', filePath]);
    run('ruff', ['check', '--fix', filePath]);
  }
}

process.stdin.setEncoding('utf8');
process.stdin.on('data', chunk => {
  if (raw.length < MAX_STDIN) {
    raw += chunk.substring(0, MAX_STDIN - raw.length);
  }
});

process.stdin.on('end', () => {
  try {
    const input = JSON.parse(raw);
    const filePath = String(input.tool_input?.file_path || '');
    maybeRunQualityGate(filePath);
  } catch {
    // Ignore parse errors — pass through
  }

  process.stdout.write(raw);
});
