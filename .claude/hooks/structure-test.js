'use strict';

/**
 * structure-test.js — リポジトリ構造整合性チェック（単体実行 / CI 用）
 *
 * master・配布先プロジェクトの両方で同一に動作する。
 *
 * 違反（exit 1）:
 *   - docs/adr/ に ADR ファイルが存在する
 *   - .claude/settings.json が有効な JSON である
 *   - .claude/hooks/ 内の全 .js ファイルに構文エラーがない
 *   - ドキュメントの相対リンクが実在する（docs/ + ルート .md + .claude/ 配下の .md）
 *
 * 警告（exit 0、stderr に出力）:
 *   - 知識グラフの孤立ノード: CLAUDE.md から辿れない docs/ 配下の .md
 */

const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');

const CLAUDE_DIR = '.claude';

// ─── 共通ユーティリティ ──────────────────────────────────────────────────────

/** dir 配下の .md ファイルを再帰的に収集する */
function collectMdFiles(dir) {
  if (!fs.existsSync(dir)) return [];
  const files = [];
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const abs = path.join(dir, entry.name);
    if (entry.isDirectory()) files.push(...collectMdFiles(abs));
    else if (entry.name.endsWith('.md')) files.push(abs);
  }
  return files;
}

/** .md ファイルから相対リンクの参照先（絶対パス）を抽出する（コードブロック除外） */
function extractRelativeLinks(filePath) {
  const raw = fs.readFileSync(filePath, 'utf8');
  const content = raw.replace(/```[\s\S]*?```/g, '');
  const linkRegex = /\[([^\]]*)\]\(([^)]+)\)/g;
  const dir = path.dirname(filePath);
  const links = [];
  let match;

  while ((match = linkRegex.exec(content)) !== null) {
    const href = match[2].trim();
    if (/^https?:\/\//.test(href) || href.startsWith('#') || href.startsWith('mailto:')) continue;
    const filePart = href.split('#')[0];
    if (!filePart) continue;
    links.push({ href: filePart, resolved: path.resolve(dir, filePart) });
  }

  return links;
}

/** リンク検査対象の .md ファイル一覧（docs/ + ルート直下 + .claude/ 配下） */
function collectCheckTargets(root) {
  const targets = [...collectMdFiles(path.join(root, 'docs'))];

  for (const entry of fs.readdirSync(root, { withFileTypes: true })) {
    if (entry.isFile() && entry.name.endsWith('.md')) {
      targets.push(path.join(root, entry.name));
    }
  }

  targets.push(...collectMdFiles(path.join(root, CLAUDE_DIR)));
  return targets;
}

// ─── 個別チェック関数 ────────────────────────────────────────────────────────

/**
 * docs/adr/ ディレクトリに ADR ファイル (.md) が存在するか検証する
 * @param {string} [root]
 * @returns {{ message: string, fix: string } | null}
 */
function checkAdrExists(root = process.cwd()) {
  const adrDir = path.join(root, 'docs', 'adr');

  if (!fs.existsSync(adrDir)) {
    return {
      message: 'docs/adr/ ディレクトリが存在しません',
      fix: 'docs/adr/ を作成し、最低 1 つの ADR ファイル（ADR-NNN-title.md）を追加してください',
    };
  }

  const adrFiles = fs.readdirSync(adrDir).filter(f => f.endsWith('.md'));
  if (adrFiles.length === 0) {
    return {
      message: 'docs/adr/ に ADR ファイルが存在しません',
      fix: 'アーキテクチャ上の決定を ADR-001-title.md 形式で記録してください',
    };
  }

  return null;
}

/**
 * .claude/settings.json が有効な JSON であるか検証する
 * @param {string} [root]
 * @returns {{ message: string, fix: string } | null}
 */
function checkSettingsJson(root = process.cwd()) {
  const settingsPath = path.join(root, CLAUDE_DIR, 'settings.json');
  if (!fs.existsSync(settingsPath)) return null;

  try {
    JSON.parse(fs.readFileSync(settingsPath, 'utf8'));
    return null;
  } catch (err) {
    return {
      message: `.claude/settings.json が有効な JSON ではありません: ${err.message}`,
      fix: '.claude/settings.json の構文エラーを修正してください（JSON バリデーターで確認を推奨）',
    };
  }
}

/**
 * .claude/hooks/ 内の全 .js ファイルに構文エラーがないか検証する
 * @param {string} [root]
 * @returns {Array<{ message: string, fix: string }>}
 */
function checkHookSyntax(root = process.cwd()) {
  const hooksDir = path.join(root, CLAUDE_DIR, 'hooks');
  if (!fs.existsSync(hooksDir)) return [];

  const violations = [];
  const jsFiles = fs.readdirSync(hooksDir).filter(f => f.endsWith('.js'));

  for (const file of jsFiles) {
    const filePath = path.join(hooksDir, file);
    try {
      execFileSync(process.execPath, ['--check', filePath], { stdio: 'pipe' });
    } catch (err) {
      const stderr = err.stderr ? err.stderr.toString().trim() : String(err.message);
      violations.push({
        message: `.claude/hooks/${file} に構文エラーがあります: ${stderr.split('\n')[0]}`,
        fix: `.claude/hooks/${file} の構文エラーを修正してください`,
      });
    }
  }

  return violations;
}

/**
 * ドキュメントの相対リンク整合性を検証する
 * 対象: docs/ 配下・ルート直下・.claude/ 配下のすべての .md
 * @param {string} [root]
 * @returns {Array<{ message: string, fix: string }>}
 */
function checkDocLinks(root = process.cwd()) {
  const violations = [];

  for (const filePath of collectCheckTargets(root)) {
    for (const link of extractRelativeLinks(filePath)) {
      if (!fs.existsSync(link.resolved)) {
        violations.push({
          message: `リンク切れ: ${path.relative(root, filePath)} → ${link.href}`,
          fix: `${link.href} を作成するか、リンクを修正してください`,
        });
      }
    }
  }

  return violations;
}

/**
 * 知識グラフの到達性チェック（グラフエンジニアリング）
 * CLAUDE.md を根ノード、相対リンクをエッジとする有向グラフを BFS で辿り、
 * docs/ 配下で到達できない .md（孤立ノード）を警告として返す。
 * 孤立ノードはエージェントのコンテキストから発見できないため、実質存在しないのと同じ。
 * @param {string} [root]
 * @returns {Array<{ message: string, fix: string }>}
 */
function checkDocGraph(root = process.cwd()) {
  const rootDoc = path.join(root, 'CLAUDE.md');
  if (!fs.existsSync(rootDoc)) return [];

  const visited = new Set();
  const queue = [rootDoc];

  while (queue.length > 0) {
    const current = queue.shift();
    if (visited.has(current)) continue;
    visited.add(current);

    if (!fs.existsSync(current) || !current.endsWith('.md')) continue;

    for (const link of extractRelativeLinks(current)) {
      if (visited.has(link.resolved) || !fs.existsSync(link.resolved)) continue;
      // リンク先がディレクトリの場合は配下の .md をノードとして展開する
      if (fs.statSync(link.resolved).isDirectory()) {
        for (const child of collectMdFiles(link.resolved)) queue.push(child);
      } else {
        queue.push(link.resolved);
      }
    }
  }

  const warnings = [];
  for (const doc of collectMdFiles(path.join(root, 'docs'))) {
    if (!visited.has(doc)) {
      const rel = path.relative(root, doc);
      warnings.push({
        message: `孤立ドキュメント: ${rel} は CLAUDE.md から辿れません`,
        fix: 'CLAUDE.md から到達可能なドキュメントからリンクするか、不要なら削除してください',
      });
    }
  }

  return warnings;
}

// ─── 全チェック実行 ──────────────────────────────────────────────────────────

function runAll(root = process.cwd()) {
  const violations = [];

  const adr = checkAdrExists(root);
  if (adr) violations.push({ check: 'adr-exists', ...adr });

  const settings = checkSettingsJson(root);
  if (settings) violations.push({ check: 'settings-json', ...settings });

  violations.push(
    ...checkHookSyntax(root).map(v => ({ check: 'hook-syntax', ...v }))
  );

  violations.push(
    ...checkDocLinks(root).map(v => ({ check: 'doc-links', ...v }))
  );

  return violations;
}

// ─── エクスポート ────────────────────────────────────────────────────────────

module.exports = {
  checkAdrExists,
  checkSettingsJson,
  checkHookSyntax,
  checkDocLinks,
  checkDocGraph,
  runAll,
};

// ─── メイン実行 ──────────────────────────────────────────────────────────────

if (require.main === module) {
  const violations = runAll();
  const warnings = checkDocGraph();

  warnings.forEach(w => {
    process.stderr.write(`[structure-test] 警告: ${w.message}\n  推奨: ${w.fix}\n`);
  });

  if (violations.length === 0) {
    process.stdout.write(
      `[structure-test] すべてのチェックが通過しました${warnings.length > 0 ? `（警告 ${warnings.length} 件）` : ''}\n`
    );
    process.exit(0);
  }

  violations.forEach(v => {
    process.stderr.write(`[structure-test] 違反: ${v.message}\n  修復手順: ${v.fix}\n`);
  });
  process.exit(1);
}
