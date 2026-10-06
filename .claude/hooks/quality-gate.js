#!/usr/bin/env node
/**
 * Quality Gate Hook (PostToolUse: Edit | Write | MultiEdit)
 *
 * Runs lightweight format/lint checks after file edits.
 * - TypeScript/JS/CSS/JSON/Markdown: the nearest biome.json(c) between the file and the project root
 *   → Biome run from that directory (local binary preferred). No biome config → the nearest Prettier
 *   config (.prettierrc*, prettier.config.*, or a "prettier" key in package.json) → Prettier.
 *   Neither configured → nothing: a project that has not chosen a formatter keeps its own style.
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
const PRETTIER_CONFIGS = [
  '.prettierrc', '.prettierrc.json', '.prettierrc.json5', '.prettierrc.yaml', '.prettierrc.yml', '.prettierrc.toml',
  '.prettierrc.js', '.prettierrc.cjs', '.prettierrc.mjs', '.prettierrc.ts',
  'prettier.config.js', 'prettier.config.cjs', 'prettier.config.mjs', 'prettier.config.ts',
];

/**
 * startDir から root まで上位へ辿り、matches が真を返す最初のディレクトリを返す
 * @param {string} startDir
 * @param {string} root この上は探さない
 * @param {(dir: string) => boolean} matches
 * @returns {string | null}
 */
function findUpWhere(startDir, root, matches) {
  const stop = path.resolve(root);
  let dir = path.resolve(startDir);

  while (dir === stop || dir.startsWith(stop + path.sep)) {
    if (matches(dir)) return dir;
    if (dir === stop) break;
    dir = path.dirname(dir);
  }
  return null;
}

/**
 * startDir から root まで上位へ辿り、names のいずれかを含む最初のディレクトリを返す
 * @param {string} startDir
 * @param {string[]} names
 * @param {string} root この上は探さない
 * @returns {string | null}
 */
function findUp(startDir, names, root) {
  return findUpWhere(startDir, root, dir => names.some(name => fs.existsSync(path.join(dir, name))));
}

/** dir に Prettier の設定（設定ファイル、または package.json の prettier キー）があるか */
function hasPrettierConfig(dir) {
  if (PRETTIER_CONFIGS.some(name => fs.existsSync(path.join(dir, name)))) return true;
  try {
    return 'prettier' in JSON.parse(fs.readFileSync(path.join(dir, 'package.json'), 'utf8'));
  } catch {
    // package.json がない・読めない場合は、Prettier を選んでいないものとして扱う
    return false;
  }
}

/** dir の node_modules/.bin にあるローカル実行ファイルを優先し、なければ npx で実行する */
function localOrNpx(dir, bin, args) {
  const local = path.join(dir, 'node_modules', '.bin', bin);
  return fs.existsSync(local)
    ? { command: local, args, cwd: dir }
    : { command: 'npx', args: [bin, ...args], cwd: dir };
}

/**
 * プロジェクトのルートを返す。作業ディレクトリはサブディレクトリのことがあるので CLAUDE_PROJECT_DIR を優先する
 * @param {NodeJS.ProcessEnv} env
 * @param {string} cwd
 * @returns {string}
 */
function resolveRoot(env, cwd) {
  return env.CLAUDE_PROJECT_DIR || cwd;
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
    const startDir = path.dirname(filePath);
    const biomeDir = findUp(startDir, BIOME_CONFIGS, root);
    if (biomeDir) return [localOrNpx(biomeDir, 'biome', ['check', '--write', filePath])];

    // 設定のないプロジェクトを Prettier の既定値で整形すると、そのプロジェクトのスタイルを壊す
    const prettierDir = findUpWhere(startDir, root, hasPrettierConfig);
    return prettierDir ? [localOrNpx(prettierDir, 'prettier', ['--write', filePath])] : [];
  }

  if (ext === '.py') {
    return [
      { command: 'ruff', args: ['format', filePath], cwd: root },
      { command: 'ruff', args: ['check', '--fix', filePath], cwd: root },
    ];
  }

  return [];
}

module.exports = { findUp, planFormat, resolveRoot };

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
      const root = resolveRoot(process.env, process.cwd());
      for (const step of planFormat(path.resolve(root, filePath), root)) {
        spawnSync(step.command, step.args, { cwd: step.cwd, encoding: 'utf8', env: process.env });
      }
    } catch {
      // Ignore parse errors — nothing to format
    }
  });
}
