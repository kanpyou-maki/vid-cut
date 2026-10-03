#!/usr/bin/env node
/**
 * Quality Gate Hook (PostToolUse: Edit | Write | MultiEdit)
 *
 * Runs lightweight format/lint checks after file edits.
 * - TypeScript/JS/CSS/JSON/Markdown: the nearest biome.json(c) between the file and the project root
 *   → Biome run from that directory (local binary preferred). No biome config → Prettier fallback.
 * - Python: ruff format + ruff check
 *
 * Searching from the edited file (not only the project root) supports layouts such as
 * frontend/biome.json + backend/pyproject.toml.
 *
 * No external dependencies — copy to .claude/hooks/ and reference from settings.json.
 */

'use strict';

const fs = require('fs');
const path = require('path');
const { spawnSync } = require('child_process');

const MAX_STDIN = 1024 * 1024;
const WEB_EXTENSIONS = ['.ts', '.tsx', '.js', '.jsx', '.json', '.md', '.css'];
const BIOME_CONFIGS = ['biome.json', 'biome.jsonc'];

/**
 * startDir から root まで上位へ辿り、names のいずれかを含む最初のディレクトリを返す
 * @param {string} startDir
 * @param {string[]} names
 * @param {string} root この上は探さない
 * @returns {string | null}
 */
function findUp(startDir, names, root) {
  const stop = path.resolve(root);
  let dir = path.resolve(startDir);

  while (dir === stop || dir.startsWith(stop + path.sep)) {
    if (names.some(name => fs.existsSync(path.join(dir, name)))) return dir;
    if (dir === stop) break;
    dir = path.dirname(dir);
  }
  return null;
}

/** dir の node_modules/.bin にあるローカル実行ファイルを優先し、なければ npx で実行する */
function localOrNpx(dir, bin, args) {
  const local = path.join(dir, 'node_modules', '.bin', bin);
  return fs.existsSync(local)
    ? { command: local, args, cwd: dir }
    : { command: 'npx', args: [bin, ...args], cwd: dir };
}

/**
 * 編集したファイルに対して実行する整形コマンドの一覧を返す（実行はしない）
 * @param {string} filePath
 * @param {string} root プロジェクトのルート
 * @returns {{ command: string, args: string[], cwd: string }[]}
 */
function planFormat(filePath, root) {
  if (!filePath || !fs.existsSync(filePath)) return [];

  const ext = path.extname(filePath).toLowerCase();

  if (WEB_EXTENSIONS.includes(ext)) {
    const biomeDir = findUp(path.dirname(filePath), BIOME_CONFIGS, root);
    return biomeDir
      ? [localOrNpx(biomeDir, 'biome', ['check', '--write', filePath])]
      : [{ command: 'npx', args: ['prettier', '--write', filePath], cwd: root }];
  }

  if (ext === '.py') {
    return [
      { command: 'ruff', args: ['format', filePath], cwd: root },
      { command: 'ruff', args: ['check', '--fix', filePath], cwd: root },
    ];
  }

  return [];
}

module.exports = { findUp, planFormat };

if (require.main === module) {
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
      const filePath = String(input.tool_input?.file_path || '');
      const root = process.cwd();
      for (const step of planFormat(path.resolve(root, filePath), root)) {
        spawnSync(step.command, step.args, { cwd: step.cwd, encoding: 'utf8', env: process.env });
      }
    } catch {
      // Ignore parse errors — pass through
    }

    process.stdout.write(raw);
  });
}
