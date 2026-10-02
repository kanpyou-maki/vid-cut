#!/usr/bin/env node
/**
 * TypeScript Type Check Hook (PostToolUse: Edit)
 *
 * Runs tsc --noEmit after editing .ts/.tsx files and reports errors
 * related to the edited file only.
 *
 * No external dependencies — copy to .claude/hooks/ and reference from settings.json.
 */

'use strict';

const { execFileSync } = require('child_process');
const fs = require('fs');
const path = require('path');

const MAX_STDIN = 1024 * 1024;
let data = '';

process.stdin.setEncoding('utf8');
process.stdin.on('data', chunk => {
  if (data.length < MAX_STDIN) {
    data += chunk.substring(0, MAX_STDIN - data.length);
  }
});

process.stdin.on('end', () => {
  try {
    const input = JSON.parse(data);
    const filePath = input.tool_input?.file_path;

    if (filePath && /\.(ts|tsx)$/.test(filePath)) {
      const resolvedPath = path.resolve(filePath);
      if (fs.existsSync(resolvedPath)) {
        // Walk up directory tree to find nearest tsconfig.json (max 20 levels)
        let dir = path.dirname(resolvedPath);
        const root = path.parse(dir).root;
        let depth = 0;

        while (dir !== root && depth < 20) {
          if (fs.existsSync(path.join(dir, 'tsconfig.json'))) break;
          dir = path.dirname(dir);
          depth++;
        }

        if (fs.existsSync(path.join(dir, 'tsconfig.json'))) {
          try {
            const npxBin = process.platform === 'win32' ? 'npx.cmd' : 'npx';
            execFileSync(npxBin, ['tsc', '--noEmit', '--pretty', 'false'], {
              cwd: dir,
              encoding: 'utf8',
              stdio: ['pipe', 'pipe', 'pipe'],
              timeout: 30000,
            });
          } catch (err) {
            // tsc exits non-zero on errors — filter to edited file only
            const output = (err.stdout || '') + (err.stderr || '');
            const relPath = path.relative(dir, resolvedPath);
            const candidates = new Set([filePath, resolvedPath, relPath]);

            const relevantLines = output
              .split('\n')
              .filter(line => [...candidates].some(c => line.includes(c)))
              .slice(0, 10);

            if (relevantLines.length > 0) {
              console.error(`[Hook] TypeScript errors in ${path.basename(filePath)}:`);
              relevantLines.forEach(line => console.error(line));
            }
          }
        }
      }
    }
  } catch {
    // Invalid input — pass through
  }

  process.stdout.write(data);
  process.exit(0);
});
