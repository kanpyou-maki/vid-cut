# CLAUDE.md

<!-- 100行以内を維持すること（ARCH-005） -->

Claude Code の作業指示。**常に日本語で応答すること。**
セッション開始時は `PROJECT_STATUS.md` を最初に読んで状態を復元すること。

## プロジェクト概要

**vid-cut**: Udemy 用に録画した mov（画面録画 + 日本語ナレーション）から、無音・フィラー・言い直しを
自動検出してカットし、Premiere XML（FCP7 xmeml）として書き出すローカルアプリ。
独自の強みは `claude -p` による**言い直しの自動検出**。要件は [PRD](./docs/prd.md)、設計は [Design Doc](./docs/design.md)、経緯は [kickoff](./docs/references/kickoff.md)。

- **技術スタック:** Python 3.12（uv / FastAPI / mlx-whisper・WhisperX・Silero VAD / ffmpeg）+ TypeScript（React / Vite）— [ADR-001](./docs/adr/ADR-001-language-and-stack.md)
- **構成:** `backend/`（uv、解析パイプライン + API）、`frontend/`（npm、編集 UI）。各 README に開発コマンド
- **テスト:** `.claude/harness.json` の `commands.test`（backend は pytest、frontend は vitest）
- **前提ツール:** ffmpeg、uv、Node.js、ログイン済みの `claude` CLI
- **検証素材:** `~/Desktop/s05-12sample.mov`。正解データは `docs/references/prototype/`

## ナビゲーション

| ドキュメント                                                           | 内容                                                         |
| ---------------------------------------------------------------------- | ------------------------------------------------------------ |
| [ARCHITECTURE.md](./ARCHITECTURE.md)                                   | ディレクトリ構造・依存ルール・アーキテクチャ規則             |
| [docs/golden-rules.md](./docs/golden-rules.md)                         | 不変の品質原則（GC エージェントが検証）                      |
| [docs/friction-log.md](./docs/friction-log.md)                         | 摩擦ログ（ハーネス改善の入力）                               |
| [docs/QUALITY_SCORE.md](./docs/QUALITY_SCORE.md)                       | 品質スコア・ギャップ追跡                                     |
| [docs/PLANS.md](./docs/PLANS.md)                                       | 実行プラン一覧                                               |
| [docs/design-docs/core-beliefs.md](./docs/design-docs/core-beliefs.md) | コーディング原則・エージェントファースト設計思想             |
| [docs/adr/](./docs/adr/)                                               | アーキテクチャ決定レコード                                   |
| [PROJECT_STATUS.md](./PROJECT_STATUS.md)                               | 現在の進捗状態（毎回更新）                                   |
| [docs/references/kickoff.md](./docs/references/kickoff.md)             | キックオフ資料（目的・ユーザー決定事項・プロトタイプの知見） |

## 開発ワークフロー

**Discussion → Document → TDD** のサイクルで進める。フェーズのスキップ禁止。

| フェーズ        | 内容                      | 使用エージェント               |
| --------------- | ------------------------- | ------------------------------ |
| 1. 議論         | 要件整理・方針確定        | `architect`, `planner`         |
| 2. ドキュメント | PRD・Design Doc・ADR 作成 | `doc-updater`                  |
| 3. 実装         | TDD（RED→GREEN→REFACTOR） | `tdd-guide`, `code-reviewer`   |
| 4. メンテナンス | 技術負債解消・GC          | `refactor-cleaner`, `gc-agent` |

## 標準コマンド

コマンドは `.claude/harness.json` に定義されている。ハードコードせず、そこから読むこと。

```bash
# テストコマンドの取得例
node -pe "require('./.claude/harness.json').commands.test"
```

| ツール                                    | 用途                                  |
| ----------------------------------------- | ------------------------------------- |
| `.claude/harness.json` の `commands.test` | テスト実行                            |
| `node .claude/hooks/arch-lint.js`         | アーキテクチャ規則検証                |
| `node .claude/hooks/structure-test.js`    | 構造整合性・知識グラフ検証            |
| `gh pr create` / `gh pr list`             | PR の作成・確認                       |
| スキル (`.claude/skills/*/SKILL.md`)      | review-loop、improve-harness 等の手順 |

## エージェント一覧

### 開発サポート

| エージェント       | 役割                                     | 起動トリガー             |
| ------------------ | ---------------------------------------- | ------------------------ |
| `architect`        | システム設計・ADR 起草                   | Phase 1 — 設計判断       |
| `planner`          | タスク分解・実行プラン作成               | Phase 1 — 方針合意後     |
| `doc-updater`      | PRD・Design Doc・ADR 作成                | Phase 2 — ドキュメント化 |
| `tdd-guide`        | TDD ワークフロー・テスト設計             | Phase 3 — コーディング   |
| `code-reviewer`    | コード品質・パターン確認（アドバイザリ） | Phase 3 — 参考意見       |
| `refactor-cleaner` | 技術負債・重複除去                       | Phase 4 — メンテナンス   |
| `gc-agent`         | 黄金原則逸脱検知・修正 PR 作成           | Phase 4 — 定期実行       |

### レビュアー（Ralph Wiggum ループ）

PR 作成前に `.claude/skills/review-loop/SKILL.md` の手順で全員を通過させること。

| エージェント        | ステージ | 審査観点                                 |
| ------------------- | -------- | ---------------------------------------- |
| `self-reviewer`     | Stage 0  | 実装の自己批判的評価                     |
| `arch-reviewer`     | Stage 1  | アーキテクチャ規則（ARCH-001〜006）      |
| `style-reviewer`    | Stage 1  | コーディングスタイル・命名・debug コード |
| `test-reviewer`     | Stage 1  | テストカバレッジ≥80%・独立性             |
| `security-reviewer` | Stage 2  | OWASP Top 10・シークレット漏洩           |
| `docs-reviewer`     | Stage 2  | 実装↔ドキュメント整合性・ADR 最新性      |

## ハーネスの自己改善

エージェント設定（`.claude/` 配下）自体もこのリポジトリの改善対象である。

- 繰り返す摩擦は `docs/friction-log.md` に記録すること
- 蓄積した摩擦は `improve-harness` スキルで設定改善に変換すること
- 汎用的な改善は `sync-upstream` スキルで master へ還元すること

## プロジェクト状態管理

`PROJECT_STATUS.md` をタスク完了・フェーズ移行のたびに更新すること。
