# プロジェクト状態

> Claude Code が自律的に管理するファイル。タスク完了・フェーズ移行のたびに更新すること。
> セッション開始時は必ずこのファイルを読んで状態を復元すること。

## 現在のフェーズ

<!-- 選択肢: 議論中 | ドキュメント作成中 | 実装中 | レビュー中 | メンテナンス中 | 完了 -->

議論中

## 概要

vid-cut: Udemy 用の録画（mov）から無音・フィラー・言い直しを自動検出してカットし、Premiere XML で書き出すローカルアプリ。
bootstrap が完了し、MVP の要件整理（Phase 1）を始める段階。

## 完了済み

- [x] bootstrap（CLAUDE.md / ARCHITECTURE.md / harness.json のカスタマイズ、.gitignore）— 2026-10-03
- [x] 言語選定の評価 → [ADR-001](./docs/adr/ADR-001-language-and-stack.md)（提案中）

## 進行中

- [ ] [PLAN-20261003-mvp-discovery](./docs/exec-plans/active/PLAN-20261003-mvp-discovery.md)

## 次にやること

- [ ] ADR-001（Python + TypeScript の据え置き）の承認
- [ ] MVP のスコープと成功指標の議論
- [ ] PRD 作成 (`docs/prd.md`)
- [ ] Design Doc 作成 (`docs/design.md`)
- [ ] ADR: 文字起こしエンジン、可変フレームレート素材と Premiere XML
- [ ] 環境準備（uv の導入、`claude` CLI の再ログイン）→ backend/frontend のスキャフォールド作成

## 決定事項

| #   | 決定内容                                                                      | 理由                                                           | ADR               |
| --- | ----------------------------------------------------------------------------- | -------------------------------------------------------------- | ----------------- |
| 1   | 仕上げは Premiere Pro。Premiere XML（xmeml）の書き出しを優先し、MP4 は補助    | ユーザー決定（kickoff）                                        | —                 |
| 2   | テロップは MVP から外すが、データモデルは文字単位のタイミングを前提に設計する | ユーザー決定（kickoff）                                        | —                 |
| 3   | 「カット」の合図は使わない                                                    | 撮影済み素材が多く、合図があってもカット開始点が明確にならない | —                 |
| 4   | 言い直しの判定は `claude -p`（サブスクの範囲内）                              | 費用を避ける                                                   | —                 |
| 5   | Python（パイプライン + API）+ TypeScript（UI）。Tauri 化は保留                | 音声 ML は Python、編集 UI は Web が最適                       | ADR-001（提案中） |

## ブロッカー

_なし_（uv 未導入と `claude` CLI の OAuth 期限切れは、実装開始までに解消すればよい）

## メモ

- 要件の入力: [docs/references/kickoff.md](./docs/references/kickoff.md)。プロトタイプと正解データ: `docs/references/prototype/`
- harness.json の test/typecheck/lint は `backend/` と `frontend/` を作るまで失敗する（想定どおり）
- quality-gate フックは `.md` の編集時にも prettier を走らせ、表を整形し直す
