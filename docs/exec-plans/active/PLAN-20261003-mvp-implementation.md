# PLAN-20261003-mvp-implementation

**ステータス:** active
**作成日:** 2026-10-03
**完了日:** —

## 目標

[PRD](../../prd.md) の Must（US-01〜US-11）を [Design Doc](../../design.md) に従って TDD で実装し、
実際の撮影素材 3 本による人の受け入れチェック（PRD 3-2）に合格する。

## 進め方

- マイルストーンごとにブランチを切り、review-loop を通して PR にする（`feat/m1-domain` など）
- 依存の内側から作る: domain → adapters → pipeline / jobs → API → frontend
- ML（mlx-whisper・WhisperX・Silero）と `claude -p` は ports の背後に置き、unit テストでは偽の実装を使う。
  実物を使うテストは `@pytest.mark.ml` を付けて既定では除外する
- 検証素材 `~/Desktop/s05-12sample.mov` は、各マイルストーンの最後の手動確認に使う

## タスク一覧

### M0: 土台（`chore/m0-scaffold`）

- [x] `backend/`: uv プロジェクト（Python 3.12）、`src/vidcut/` の空パッケージ、pytest・pytest-cov・ruff・mypy。ML の依存は extras `ml` に分ける
- [x] `frontend/`: Vite + React + TypeScript、vitest・Testing Library・Biome。`test` / `coverage` / `typecheck` / `lint` の npm scripts
- [x] `.claude/harness.json` の全コマンドが空のテストで通ることを確認
- [x] quality-gate フックが `frontend/biome.json` を見つけられるか確認→ ルートにしか探さないため FRIC-003 に記録。Biome を Prettier 互換の設定にして回避

### M1: domain（`feat/m1-domain`）

- [x] データモデル（Recording, SpeechChunk, Token, Silence, Lecture, CutSuggestion, EditState, ReviewMark, Job）。frozen dataclass、時刻は整数ミリ秒
- [x] 実際に削除される区間の計算（自動の候補 − 戻したもの ∪ 手動の削除）
- [x] 残す区間の計算（余白 前 150ms・後 250ms を無音の中に収める、重なりの統合）
- [x] フレームへの丸め（開始は切り捨て・終了は切り上げ、60fps）
- [x] 録画ファイル内の時刻 → 出力の時刻の変換（プレビューと将来の字幕用）
- [x] 判定のやり直し時の `overrides` の引き継ぎ

### M2: 外部ツールの土台（`feat/m2-adapters`）

- [ ] ffmpeg adapter: probe、解析用の音声、proxy、波形のピーク値、中間素材（`tpad` で最後のフレームを延ばす）
- [ ] 可変フレームレートの回帰テスト（S-1 の人工素材を lavfi で生成し、映像と音声の長さの一致、白枠とビープの同期を検証）
- [ ] SQLite のリポジトリ（録画ファイル・レクチャー・編集状態・ジョブ）
- [ ] ジョブ表と worker のループ（1 件ずつ、優先度、起動時の `running` → `queued` の復旧、失敗時の記録）

### M3: 解析パイプライン（`feat/m3-analysis`）

- [ ] 無音検出（Silero VAD + 音量）と発話チャンクへの分割
- [ ] 文字起こし adapter（mlx-whisper large-v3-turbo、チャンクごと、ヒント文、`avg_logprob`）
- [ ] 位置合わせ adapter（WhisperX、日本語、文字単位）
- [ ] フィラー検出（辞書 + 前後の無音）と要確認の印（低確信度・未認識の発話）
- [ ] `analyze_recording` ジョブ（段ごとの生成物のキャッシュと再開）、`make_mezzanine` ジョブ
- [ ] CLI: `vidcut analyze <paths...> [--wait]`、`vidcut worker`
- [ ] 手動確認: 検証素材で解析時間が 5 分以内（中間素材を除く）

### M4: 言い直しの判定（`feat/m4-judge`）

- [ ] claude adapter（中立な作業ディレクトリ、引数リスト、タイムアウト、未ログインの検出）
- [ ] 判定の指示文（プロトタイプを出発点に、ファイルの境目の扱いを追加）と出力スキーマの検証・再試行
- [ ] チャンク数が多い場合の窓分割と統合
- [ ] `judge_lecture` ジョブ
- [ ] `vidcut eval judge`: 正解データとの適合率・再現率（目標 ≥ 90% / ≥ 80%）

### M5: 書き出し（`feat/m5-export`）

- [ ] Premiere XML（xmeml v4、複数の録画ファイル、映像 1 + 音声 2 トラック、60fps）
- [ ] MP4（中間素材から trim / concat、h264_videotoolbox）
- [ ] `export_premiere` / `export_mp4` ジョブ（中間素材の完成を待つ）
- [ ] 手動確認: 検証素材の書き出しを Premiere で読み込み、音ズレがないこと

### M6: API（`feat/m6-api`）

- [ ] FastAPI のアプリと `{success, data, error}` の形、127.0.0.1 のみ
- [ ] ローカル API の防御（Design Doc 3-5-1: Host / Origin の検証、起動ごとのトークン、パスの正規化）
- [ ] `/api/fs`（ホーム配下のみ、パスの検証）、`/api/imports`、`/api/lectures`（一覧・詳細・merge・order・split）、`/api/lectures/{id}/edits`（楽観的排他）、`/api/lectures/{id}/exports`、`/api/jobs`（一覧・retry）
- [ ] `/api/recordings/{id}/proxy`（Range 対応）、`/peaks`
- [ ] `vidcut serve`（API サーバー + worker の起動、ビルド済み frontend の配信）
- [ ] OpenAPI → `openapi-typescript` で frontend の型を生成

### M7: frontend（`feat/m7-*` に分割）

- [ ] 素材一覧: レクチャーの一覧と状態、投入ダイアログ（フォルダブラウザ）、まとめる・並べ替え・解除、失敗の再実行
- [ ] 編集画面の骨組み: 3 ペインのレイアウト、データ取得
- [ ] 文字起こし: トークン表示、選択 → 削除、復活、種類ごとの色、要確認の印と移動キー、判定理由の表示
- [ ] 波形: wavesurfer.js + ピーク値 + regions による削除区間の表示
- [ ] プレビュー: 録画ファイルの切り替え、削除区間のスキップ（`requestVideoFrameCallback`）
- [ ] 編集状態: `useReducer` + 履歴による undo / redo、1 秒遅延の自動保存
- [ ] 書き出しボタンと保存先の表示

### M8: E2E と受け入れ（`test/m8-e2e`）

- [ ] Playwright: 投入 → 解析 → 編集 → 書き出し（ML と判定は偽の実装に差し替え）
- [ ] 実際の撮影素材 3 本で受け入れチェック（PRD 3-2）: 誤削除は 1 本あたり 2 件以下、作業時間は手作業の半分以下、書き出しの音ズレ 0 件
- [ ] フィラーを含む素材が手に入れば、フィラー検出を検証（Design Doc D-5）

## 完了条件

- [ ] すべてのテストが通過し、カバレッジが 80% 以上
- [ ] 受け入れチェック（PRD 3-2）に合格
- [ ] 関連ドキュメントが更新されている
- [ ] `QUALITY_SCORE.md` が更新されている

## 進捗メモ

- 2026-10-03: M0 完了（`chore/m0-scaffold`）。backend: Python 3.12・pytest・ruff・mypy（strict）。frontend: React 19・Vite 8・TypeScript 6・vitest 5・Biome 2。テンプレート既定の oxlint は Biome に置き換えた
- 2026-10-03: M1 完了（`feat/m1-domain`）。domain に intervals / models / cuts / timeline / overrides。テスト 69 件、カバレッジ 100%

- スパイクのスクリプト（xmeml の最小実装、ASR の計測）は使い捨て。知見は ADR-002・ADR-003 に記録済み
- ML の初回実行ではモデルのダウンロード（合計約 3GB、5 分程度）が発生する

## 完了後の手順

1. このファイルのステータスを `completed` に変更
2. `docs/exec-plans/completed/` へ移動
3. `docs/PLANS.md` のインデックスを更新
