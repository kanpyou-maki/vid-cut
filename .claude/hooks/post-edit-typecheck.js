#!/usr/bin/env node
/**
 * TypeScript Type Check Hook (PostToolUse: Edit)
 *
 * Runs tsc --noEmit after editing .ts/.tsx files and reports errors
 * related to the edited file only.
 *
 * Errors go to stderr with exit code 2: PostToolUse stderr reaches the model only on exit 2 (ADR-005).
 *
 * A "solution style" tsconfig.json (files: [] + references, e.g. the Vite template) checks nothing
 * by itself, so each referenced project is checked with `tsc --noEmit -p <ref>` instead.
 *
 * No external dependencies — copy to .claude/hooks/ and reference from settings.json.
 */

'use strict';

const { spawnSync } = require('child_process');
const fs = require('fs');
const path = require('path');

const MAX_STDIN = 1024 * 1024;
const MAX_DEPTH = 20;
const TSC_FLAGS = ['--noEmit', '--pretty', 'false'];
const EXIT_REPORT_TO_MODEL = 2;

/**
 * ファイルの位置から上位へ辿り、tsconfig.json のあるディレクトリを返す
 * @param {string} filePath
 * @param {string} [stopDir] この上は探さない（省略時はファイルシステムのルートまで）
 * @returns {string | null}
 */
function findTsconfigDir(filePath, stopDir) {
  let dir = path.dirname(path.resolve(filePath));
  const stop = stopDir ? path.resolve(stopDir) : null;

  for (let depth = 0; depth < MAX_DEPTH; depth++) {
    if (fs.existsSync(path.join(dir, 'tsconfig.json'))) return dir;
    const parent = path.dirname(dir);
    if (parent === dir || dir === stop) return null;
    dir = parent;
  }
  return null;
}

/** tsconfig.json（コメントを含みうる）から references の path を取り出す */
function readReferencePaths(tsconfigPath) {
  const raw = fs.readFileSync(tsconfigPath, 'utf8');
  const block = raw.match(/"references"\s*:\s*\[([\s\S]*?)\]/);
  if (!block) return [];
  return [...block[1].matchAll(/"path"\s*:\s*"([^"]+)"/g)].map(m => m[1]);
}

/**
 * tsconfig の形に応じて型チェックのコマンド一覧を返す（実行はしない）
 * @param {string} dir tsconfig.json のあるディレクトリ
 * @returns {{ command: string, args: string[], cwd: string }[]}
 */
function planTypecheck(dir) {
  const localTsc = path.join(dir, 'node_modules', '.bin', 'tsc');
  const run = args => (fs.existsSync(localTsc)
    ? { command: localTsc, args, cwd: dir }
    : { command: 'npx', args: ['tsc', ...args], cwd: dir });

  const refs = readReferencePaths(path.join(dir, 'tsconfig.json'));
  if (refs.length === 0) return [run(TSC_FLAGS)];

  return refs.map(ref => {
    const target = path.resolve(dir, ref);
    const project = target.endsWith('.json') ? target : path.join(target, 'tsconfig.json');
    return run([...TSC_FLAGS, '-p', project]);
  });
}

module.exports = { findTsconfigDir, planTypecheck };

if (require.main === module) {
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

      if (filePath && /\.(ts|tsx)$/.test(filePath) && fs.existsSync(path.resolve(filePath))) {
        const resolvedPath = path.resolve(filePath);
        const dir = findTsconfigDir(resolvedPath);

        if (dir) {
          const output = planTypecheck(dir)
            .map(step => spawnSync(step.command, step.args, { cwd: step.cwd, encoding: 'utf8', timeout: 30000 }))
            .map(result => (result.stdout || '') + (result.stderr || ''))
            .join('\n');

          // tsc の出力から、編集したファイルに関するエラーだけを抜き出す
          const relPath = path.relative(dir, resolvedPath);
          const candidates = [filePath, resolvedPath, relPath];
          const relevantLines = output
            .split('\n')
            .filter(line => candidates.some(c => line.includes(c)))
            .slice(0, 10);

          if (relevantLines.length > 0) {
            console.error(`[Hook] TypeScript errors in ${path.basename(filePath)}:`);
            relevantLines.forEach(line => console.error(line));
            process.exitCode = EXIT_REPORT_TO_MODEL;
          }
        }
      }
    } catch {
      // Invalid input — nothing to check
    }
  });
}
