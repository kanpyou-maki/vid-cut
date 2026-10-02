# PLAN-20261003-mvp-discovery

**ステータス:** active
**作成日:** 2026-10-03
**完了日:** —

## 目標

[kickoff](../../references/kickoff.md) を入力に、MVP の要件と設計を確定させ、TDD で実装を始められる状態にする。
実装前に「何を MVP に入れ、何を外すか」と「データモデル（字幕を見据えた文字単位タイミング）」を合意することが目的。

## タスク一覧

- [x] bootstrap（ハーネスのカスタマイズ、言語選定 [ADR-001](../../adr/ADR-001-language-and-stack.md) の起草）
- [x] 議論: ADR-001（Python + TypeScript）の承認
- [x] 議論: MVP のスコープ → 編集画面まで含める
- [x] 議論: 成功指標 → 正解データとの一致率は暫定指標、合格判定は実素材で人が行う
- [x] PRD 作成（`docs/prd.md`）— 2026-10-03 承認
- [ ] Design Doc 作成（`docs/design.md`）: データモデル（レクチャー = 順序付きの録画ファイル群、ファイルごとの時間軸）、一括解析のジョブキュー、パイプラインの各段、API、Premiere XML と可変フレームレート素材の扱い
- [ ] ADR: 文字起こしエンジン（mlx-whisper / faster-whisper / whisper.cpp）
- [ ] ADR: Premiere XML（xmeml）での可変フレームレート素材の扱い（事前に固定フレームレート化するか）
- [ ] 環境準備: uv の導入、`claude` CLI の再ログイン（`/login`）
- [ ] `backend/` と `frontend/` のスキャフォールド作成、`.claude/harness.json` のコマンドが通ることの確認

## 完了条件

- [ ] PRD・Design Doc・必要な ADR がレビュー済みで承認されている
- [ ] `.claude/harness.json` の全コマンドが（空のテストで）通過する
- [ ] `QUALITY_SCORE.md` が更新されている

## 進捗メモ

- 2026-10-03: bootstrap 完了。言語は Python + TypeScript を据え置く（ADR-001 承認済み）。
- ローカル環境: arm64、Python 3.13（ML 互換のため uv で 3.12 を使う予定）、Node 24、ffmpeg あり、**uv 未導入**。

## 完了後の手順

1. このファイルのステータスを `completed` に変更
2. `docs/exec-plans/completed/` へ移動
3. `docs/PLANS.md` のインデックスを更新
