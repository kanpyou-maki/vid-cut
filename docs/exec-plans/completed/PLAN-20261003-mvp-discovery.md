# PLAN-20261003-mvp-discovery

**ステータス:** completed
**作成日:** 2026-10-03
**完了日:** 2026-10-03

## 目標

[kickoff](../../references/kickoff.md) を入力に、MVP の要件と設計を確定させ、TDD で実装を始められる状態にする。
実装前に「何を MVP に入れ、何を外すか」と「データモデル（字幕を見据えた文字単位タイミング）」を合意することが目的。

## タスク一覧

- [x] bootstrap（ハーネスのカスタマイズ、言語選定 [ADR-001](../../adr/ADR-001-language-and-stack.md) の起草）
- [x] 議論: ADR-001（Python + TypeScript）の承認
- [x] 議論: MVP のスコープ → 編集画面まで含める
- [x] 議論: 成功指標 → 正解データとの一致率は暫定指標、合格判定は実素材で人が行う
- [x] PRD 作成（`docs/prd.md`）— 2026-10-03 承認
- [x] Design Doc 草案（`docs/design.md`）: データモデル（レクチャー = 順序付きの録画ファイル群、ファイルごとの時間軸）、一括解析のジョブキュー、パイプラインの各段、API、Premiere XML と可変フレームレート素材の扱い
- [x] ADR 草案: ADR-002（可変フレームレート → 中間素材）、ADR-003（文字起こし）、ADR-004（実行形態）— 提案中
- [x] Design Doc の承認 — 2026-10-03（D-1 は暫定値で進め、S-1 で確認）
- [x] スパイク S-1〜S-4 を実施 — 2026-10-03
- [x] ADR-002・ADR-003 の承認（中間素材は 60fps）
- [x] 環境準備: uv の導入、`claude` CLI の再ログイン（`/login`）
- [→] `backend/` と `frontend/` のスキャフォールド作成 → [PLAN-20261003-mvp-implementation](../active/PLAN-20261003-mvp-implementation.md) の M0 に移管

## 完了条件

- [x] PRD・Design Doc・必要な ADR がレビュー済みで承認されている
- [→] `.claude/harness.json` の全コマンドが（空のテストで）通過する（M0 に移管）
- [x] `QUALITY_SCORE.md` が更新されている

## 進捗メモ

- 2026-10-03: bootstrap 完了。言語は Python + TypeScript を据え置く（ADR-001 承認済み）。
- 2026-10-03: `claude` CLI 再ログイン済み。スパイク S-4 実施 → 正解データと 3 回とも完全一致（指示文の過学習の可能性あり。Design Doc 参照）。
- 2026-10-03: S-2・S-3 実施（ADR-003 に結果）。S-1 は素材と XML を `~/VidCut/spikes/s1/` に生成済みで、ユーザーの Premiere 確認待ち。中間素材の作成が遅い問題を ADR-002 に記録。
- ローカル環境: arm64、Python 3.13（ML 互換のため uv で 3.12 を使う予定）、Node 24、ffmpeg あり、uv 0.12.22 導入済み。

## 完了後の手順

1. このファイルのステータスを `completed` に変更
2. `docs/exec-plans/completed/` へ移動
3. `docs/PLANS.md` のインデックスを更新
