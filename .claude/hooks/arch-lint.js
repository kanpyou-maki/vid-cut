'use strict';

/**
 * arch-lint.js — アーキテクチャリンタ (PostToolUse: Edit | Write)
 *
 * master・配布先プロジェクトの両方で同一に動作する（レイアウトが同型のため）。
 * ARCH-001/002 は `.claude/` 配下のみを検査対象とし、
 * 配布先プロジェクト固有のソースコードには干渉しない。
 *
 * 規則:
 *   ARCH-001 エージェント定義は .claude/agents/ にのみ配置する
 *   ARCH-002 フック実装 (.js) は .claude/ 配下では .claude/hooks/ にのみ配置する
 *   ARCH-003 .claude/rules/ のファイルは {lang}/{category}.md 形式に従う
 *   ARCH-004 .claude/settings.json のフックコマンドは $CLAUDE_PROJECT_DIR 起点で、参照先が実在する
 *   ARCH-005 CLAUDE.md は 100行以内
 *   ARCH-006 .md ファイル内の相対リンクが実在する
 *   ARCH-007 PROJECT_STATUS.md は 6KB 以内（引き継ぎメモに絞る。ADR-006）
 *
 * 違反は stderr に書き、終了コード 2 で終わる。PostToolUse の stderr がモデルに渡るのは
 * 終了コード 2 のときだけなので、0 で終わると違反が誰にも届かない（ADR-005）。
 */

const fs = require('fs');
const path = require('path');

const CLAUDE_DIR = '.claude';
const PROJECT_DIR_PREFIX = /^\$(?:CLAUDE_PROJECT_DIR|\{CLAUDE_PROJECT_DIR\})\//;
const EXIT_REPORT_TO_MODEL = 2;
const MAX_FIELD_LENGTH = 300;
const STATUS_FILE = 'PROJECT_STATUS.md';
const STATUS_FILE_MAX_BYTES = 6 * 1024;

/** filePath が root/.claude/ 配下にあるか */
function inClaudeDir(filePath, root) {
  return filePath.startsWith(path.join(root, CLAUDE_DIR) + path.sep);
}

// ─── 個別チェック関数（root を受け取りテスト可能にする） ─────────────────────

/**
 * ARCH-001: エージェント定義 (.md with `name:` frontmatter) は .claude/agents/ のみ
 * `.claude/` 配下のみ検査する（プロジェクト固有の .md には干渉しない）。
 * SKILL.md は frontmatter を持ちうるため除外する。
 * @param {string} filePath - 絶対パス
 * @param {string} [root]   - リポジトリルート（省略時は process.cwd()）
 */
function checkArch001(filePath, root = process.cwd()) {
  if (!filePath.endsWith('.md')) return null;
  if (path.basename(filePath) === 'SKILL.md') return null;
  if (!inClaudeDir(filePath, root)) return null;

  const agentsDir = path.join(root, CLAUDE_DIR, 'agents') + path.sep;
  if (filePath.startsWith(agentsDir)) return null;

  let content;
  try {
    content = fs.readFileSync(filePath, 'utf8');
  } catch {
    return null;
  }

  // frontmatter 内に `name: <value>` があるかチェック
  if (!content.startsWith('---')) return null;
  const end = content.indexOf('\n---', 3);
  if (end === -1) return null;
  const frontmatter = content.slice(0, end);
  if (!/^name:\s+\S/m.test(frontmatter)) return null;

  const rel = path.relative(root, filePath);
  return {
    rule: 'ARCH-001',
    file: rel,
    message: 'エージェント定義 (.md with name: frontmatter) は .claude/agents/ 以外に配置できません',
    fix: `.claude/agents/ へ移動してください: mv ${rel} .claude/agents/${path.basename(filePath)}`,
  };
}

/**
 * ARCH-002: .claude/ 配下の .js は .claude/hooks/ のみ（.test.js は除く）
 * `.claude/` 外のプロジェクトソースコードには干渉しない。
 * @param {string} filePath
 * @param {string} [root]
 */
function checkArch002(filePath, root = process.cwd()) {
  if (!filePath.endsWith('.js')) return null;
  if (filePath.endsWith('.test.js')) return null;
  if (!inClaudeDir(filePath, root)) return null;

  const hooksDir = path.join(root, CLAUDE_DIR, 'hooks') + path.sep;
  if (filePath.startsWith(hooksDir)) return null;

  const rel = path.relative(root, filePath);
  return {
    rule: 'ARCH-002',
    file: rel,
    message: '.claude/ 配下のフック実装 (.js) は .claude/hooks/ 以外に配置できません',
    fix: `.claude/hooks/ へ移動してください: mv ${rel} .claude/hooks/${path.basename(filePath)}`,
  };
}

/**
 * ARCH-003: .claude/rules/ のファイルは {lang}/{category}.md 形式
 * @param {string} filePath
 * @param {string} [root]
 */
function checkArch003(filePath, root = process.cwd()) {
  const rulesDir = path.join(root, CLAUDE_DIR, 'rules');
  if (!filePath.startsWith(rulesDir + path.sep)) return null;

  const rel = path.relative(rulesDir, filePath);
  const parts = rel.split(path.sep);
  if (parts.length === 2 && parts[1].endsWith('.md')) return null;

  return {
    rule: 'ARCH-003',
    file: path.relative(root, filePath),
    message: `.claude/rules/ のファイルは {lang}/{category}.md 形式に従う必要があります（現在: rules/${rel}）`,
    fix: '正しい形式の例: .claude/rules/typescript/coding-style.md',
  };
}

/**
 * フックコマンドから node スクリプトのパスを取り出す
 * @param {string} command
 * @returns {{ script: string, anchored: boolean } | null}
 *   script は $CLAUDE_PROJECT_DIR を除いたパス、anchored は $CLAUDE_PROJECT_DIR 起点かどうか
 */
function parseHookCommand(command) {
  const match = command.match(/node\s+(\S+\.js)/);
  if (!match) return null;
  const token = match[1].replace(/"/g, '');
  return { script: token.replace(PROJECT_DIR_PREFIX, ''), anchored: PROJECT_DIR_PREFIX.test(token) };
}

/**
 * ARCH-004: .claude/settings.json のフックコマンドは $CLAUDE_PROJECT_DIR 起点で、参照先が実在する
 * 相対パスのコマンドは、作業ディレクトリがプロジェクト直下でないとき起動に失敗する。
 * @param {string} [root]
 * @returns {Array<{rule, file, message, fix}>}
 */
function checkArch004(root = process.cwd()) {
  const settingsPath = path.join(root, CLAUDE_DIR, 'settings.json');
  if (!fs.existsSync(settingsPath)) return [];

  let settings;
  try {
    settings = JSON.parse(fs.readFileSync(settingsPath, 'utf8'));
  } catch {
    return [];
  }

  // 形の崩れた定義（配列でない・要素が null など）は読み飛ばす。ここで例外を出すと、ほかの規則の検査まで止まる
  const handlers = Object.values((settings && settings.hooks) || {})
    .filter(Array.isArray)
    .flat()
    .flatMap(entry => (entry && Array.isArray(entry.hooks) ? entry.hooks : []))
    .filter(Boolean);

  const violations = [];
  for (const hook of handlers) {
    const parsed = parseHookCommand(String(hook.command || ''));
    if (!parsed) continue;
    const { script, anchored } = parsed;
    if (!fs.existsSync(path.resolve(root, script))) {
      violations.push({
        rule: 'ARCH-004',
        file: '.claude/settings.json',
        message: `settings.json が存在しないフックを参照しています: ${script}`,
        fix: `${script} を作成するか、settings.json から該当エントリを削除してください`,
      });
    }
    if (!anchored && !path.isAbsolute(script)) {
      violations.push({
        rule: 'ARCH-004',
        file: '.claude/settings.json',
        message: `フックのコマンドが相対パスです（作業ディレクトリがプロジェクト直下でないと起動に失敗します）: ${script}`,
        fix: `settings.json の command を次の形に書き換えてください: node "$CLAUDE_PROJECT_DIR"/${script}`,
      });
    }
  }

  return violations;
}

/**
 * ARCH-005: CLAUDE.md は 100行以内
 * @param {string} [root]
 */
function checkArch005(root = process.cwd()) {
  const claudePath = path.join(root, 'CLAUDE.md');
  if (!fs.existsSync(claudePath)) return null;

  const content = fs.readFileSync(claudePath, 'utf8');
  // ファイル末尾の改行は行数に含めない（wc -l と同じ挙動）
  const lines = content.split('\n').length - (content.endsWith('\n') ? 1 : 0);
  if (lines <= 100) return null;

  return {
    rule: 'ARCH-005',
    file: 'CLAUDE.md',
    message: `CLAUDE.md が 100行を超えています（現在 ${lines} 行）`,
    fix: 'CLAUDE.md の詳細情報を docs/ 配下のファイルへ移動し、地図として簡素化してください',
  };
}

/**
 * ARCH-006: Markdown ファイル内の相対リンクが実在する
 * @param {string} filePath
 * @param {string} [root]
 * @returns {Array<{rule, file, message, fix}>}
 */
function checkArch006(filePath, root = process.cwd()) {
  if (!filePath.endsWith('.md')) return [];

  let content;
  try {
    content = fs.readFileSync(filePath, 'utf8');
  } catch {
    return [];
  }

  const violations = [];
  // コードブロック内のリンクは検査対象外
  const stripped = content.replace(/```[\s\S]*?```/g, '');
  // リンクのテキストから「[」を除き、参照先の長さを制限する（角括弧が大量に並ぶ入力で検査時間が二乗に増えないように）
  const linkRegex = /\[([^[\]]*)\]\(([^)]{1,2000})\)/g;
  const dir = path.dirname(filePath);
  let match;

  while ((match = linkRegex.exec(stripped)) !== null) {
    const href = match[2].trim();

    // 絶対 URL・アンカーのみ・mailto は無視
    if (/^https?:\/\//.test(href) || href.startsWith('#') || href.startsWith('mailto:')) continue;

    // フラグメント部分を除いたファイルパスを取得
    const filePart = href.split('#')[0];
    if (!filePart) continue;

    const linkedFile = path.resolve(dir, filePart);
    if (!fs.existsSync(linkedFile)) {
      violations.push({
        rule: 'ARCH-006',
        file: path.relative(root, filePath),
        message: `Markdown リンクの参照先が存在しません: ${filePart}`,
        fix: `${filePart} を作成するか、リンクを修正してください`,
      });
    }
  }

  return violations;
}

/**
 * ARCH-007: 状態ファイルは 6KB 以内
 * 毎セッション最初に読むファイルなので、いまの状態ではないもの（履歴・決定・知見）が溜まると
 * コンテキストを圧迫する。行数ではなくバイト数で測る（行数は 1 行を長くすれば通ってしまう）。
 * @param {string} [root]
 */
function checkArch007(root = process.cwd()) {
  let bytes;
  try {
    bytes = fs.statSync(path.join(root, STATUS_FILE)).size;
  } catch {
    // 状態ファイルがない・大きさを調べられない場合は検査の対象外
    return null;
  }
  if (bytes <= STATUS_FILE_MAX_BYTES) return null;

  const format = n => n.toLocaleString('en-US');
  return {
    rule: 'ARCH-007',
    file: STATUS_FILE,
    message: `${STATUS_FILE} が上限を超えています（現在 ${format(bytes)} バイト、上限 ${format(STATUS_FILE_MAX_BYTES)} バイト）`,
    fix: '載せるのは「現在のフェーズ・進行中・次にやること・人間待ち」だけです。終わった項目は消し、'
      + '決定は docs/adr/ か設計書へ、知見は docs/ の該当文書へ、繰り返すハマりどころは docs/friction-log.md へ、'
      + 'タスク分解は docs/exec-plans/ へ移してください',
  };
}

// ─── 出力フォーマット ────────────────────────────────────────────────────────

/**
 * 違反メッセージはモデルに渡る。ファイルパスやリンク先など入力由来の文字列を含むので、
 * 制御文字（改行を含む）を空白に置き換え、長さを制限して 1 行に収める
 */
function toSingleLine(text) {
  // 文字（コードポイント）単位で数える。UTF-16 の単位で切ると絵文字などが途中で割れる
  const chars = Array.from(String(text).replace(/\s*[\u0000-\u001f\u007f]+\s*/g, ' '));
  return chars.length > MAX_FIELD_LENGTH ? `${chars.slice(0, MAX_FIELD_LENGTH).join('')}…` : chars.join('');
}

function formatViolation(v) {
  return `[arch-lint] ${v.rule} 違反: ${toSingleLine(v.message)}\n  ファイル: ${toSingleLine(v.file)}\n  修復手順: ${toSingleLine(v.fix)}`;
}

// ─── 全チェック実行 ──────────────────────────────────────────────────────────

/**
 * filePath があれば、そのファイルに関係する規則だけを検査する（編集のたびに無関係な違反を繰り返し報告しない）。
 * filePath が空なら、リポジトリ全体の規則（ARCH-004・005・007）を検査する。
 */
function runChecks(filePath, root = process.cwd()) {
  const violations = [];
  let checkSettings = true;
  let checkClaudeMd = true;
  let checkStatusFile = true;

  if (filePath) {
    const abs = path.isAbsolute(filePath) ? filePath : path.join(root, filePath);
    for (const fn of [checkArch001, checkArch002, checkArch003]) {
      const v = fn(abs, root);
      if (v) violations.push(v);
    }
    violations.push(...checkArch006(abs, root));

    const hooksDir = path.join(root, CLAUDE_DIR, 'hooks') + path.sep;
    checkSettings = abs === path.join(root, CLAUDE_DIR, 'settings.json') || abs.startsWith(hooksDir);
    checkClaudeMd = abs === path.join(root, 'CLAUDE.md');
    checkStatusFile = abs === path.join(root, STATUS_FILE);
  }

  if (checkSettings) violations.push(...checkArch004(root));
  const v5 = checkClaudeMd ? checkArch005(root) : null;
  if (v5) violations.push(v5);
  const v7 = checkStatusFile ? checkArch007(root) : null;
  if (v7) violations.push(v7);

  return violations;
}

// ─── エクスポート ────────────────────────────────────────────────────────────

module.exports = {
  checkArch001,
  checkArch002,
  checkArch003,
  checkArch004,
  checkArch005,
  checkArch006,
  checkArch007,
  runChecks,
  formatViolation,
};

// ─── メイン実行（Claude Code フックとして） ──────────────────────────────────

if (require.main === module) {
  const MAX_STDIN = 1024 * 1024;
  let raw = '';

  process.stdin.setEncoding('utf8');
  process.stdin.on('data', chunk => {
    if (raw.length < MAX_STDIN) raw += chunk.substring(0, MAX_STDIN - raw.length);
  });

  process.stdin.on('end', () => {
    let filePath = '';
    try {
      const input = JSON.parse(raw);
      filePath = String(input.tool_input?.file_path || '');
    } catch {
      // stdin が空または JSON 以外の場合は無視
    }

    const violations = runChecks(filePath, process.env.CLAUDE_PROJECT_DIR || process.cwd());
    if (violations.length === 0) return;

    violations.forEach(v => process.stderr.write(formatViolation(v) + '\n'));
    process.exitCode = EXIT_REPORT_TO_MODEL;
  });
}
