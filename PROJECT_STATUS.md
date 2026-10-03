# プロジェクト状態

> Claude Code が自律的に管理するファイル。タスク完了・フェーズ移行のたびに更新すること。
> セッション開始時は必ずこのファイルを読んで状態を復元すること。

## 現在のフェーズ

<!-- 選択肢: 議論中 | ドキュメント作成中 | 実装中 | レビュー中 | メンテナンス中 | 完了 -->

実装中

## 概要

vid-cut: Udemy 用の録画（mov）から無音・フィラー・言い直しを自動検出してカットし、Premiere XML で書き出すローカルアプリ。
PRD・Design Doc が承認済み。実装計画（M0〜M8）を承認。M0〜M5 と FRIC-004 の解消は main にマージ済み（PR #1〜#8）。M6（API）を 3 本の PR に分けて実装中。GitHub: kanpyou-maki/vid-cut（private）。

## 完了済み

- [x] bootstrap（CLAUDE.md / ARCHITECTURE.md / harness.json のカスタマイズ、.gitignore）— 2026-10-03
- [x] 言語選定 → [ADR-001](./docs/adr/ADR-001-language-and-stack.md)（承認済み）— 2026-10-03
- [x] MVP のスコープと成功指標の議論 — 2026-10-03
- [x] PRD → [docs/prd.md](./docs/prd.md)（承認済み）— 2026-10-03
- [x] Design Doc → [docs/design.md](./docs/design.md)（承認済み）、ADR-004（承認済み）— 2026-10-03
- [x] スパイク S-4（判定の基準値）— 2026-10-03
- [x] uv の導入（0.12.22）— 2026-10-03
- [x] スパイク S-2・S-3（文字起こし・位置合わせ）→ ADR-003 に結果を記録 — 2026-10-03
- [x] ADR-002（中間素材・60fps）・ADR-003（mlx-whisper + WhisperX）承認 — 2026-10-03
- [x] 実装計画の承認、M0（backend / frontend の土台）— 2026-10-03
- [x] M1: domain（区間演算・データモデル・削除区間・残す区間・フレーム丸め・出力時刻・引き継ぎ。テスト 80 件 / カバレッジ 100%）— 2026-10-03
- [x] M2: 外部ツールの土台（ffmpeg adapter・可変フレームレートの回帰テスト・SQLite リポジトリ・ジョブ表と worker。テスト 226 件 / カバレッジ 99%。review-loop 全通過）— 2026-10-03
- [x] M3: 解析パイプライン（無音・VAD・mlx-whisper・WhisperX・フィラー・要確認の印・段のキャッシュ・CLI）。検証素材の解析 2 分 29 秒、正解の 69 チャンクと一致 — 2026-10-03
- [x] FRIC-004: 整形・lint は `harness.json` の `commands.lint` を正とする（ルール文書・style-reviewer・python-patterns を修正。`lint` に `ruff format --check` を追加）— 2026-10-03
- [x] M4: 言い直しの判定（claude adapter・判定の指示文と出力の検証・窓分割・`judge_lecture` ジョブ・`vidcut eval judge`）。検証素材で適合率・再現率とも 100%（実際の解析結果で 3 回）— 2026-10-03
- [x] M5: 書き出し（Premiere XML・MP4・`export_premiere` / `export_mp4` ジョブ。テスト 602 件 / カバレッジ 98%。review-loop 全通過）。検証素材の書き出しを Premiere で読み込み、音ズレなし（ユーザー確認）— 2026-10-03
- [x] スパイク S-1（Premiere XML）: 元素材の参照は不可、中間素材の参照は OK（最後のフレームを延ばす修正込み）→ ADR-002 — 2026-10-03

## 進行中

- [ ] [PLAN-20261003-mvp-implementation](./docs/exec-plans/active/PLAN-20261003-mvp-implementation.md)— M0〜M5 完了。M6 は PR 1（下ごしらえ: services と保存まわり。`feat/m6-api`）が review-loop を通過し、PR [#9](https://github.com/kanpyou-maki/vid-cut/pull/9) のマージ待ち

## 次にやること

- [ ] M6 PR 1 の PR [#9](https://github.com/kanpyou-maki/vid-cut/pull/9) のマージ（ユーザー）
- [ ] M6 PR 2（`feat/m6-api-http`。PR 1 のブランチから切る）: FastAPI のアプリ・ローカル API の防御・入力の上限・各エンドポイント・proxy（Range）と peaks。依存に fastapi・uvicorn・pydantic、dev に httpx を追加（承認済み）
- [ ] M6 PR 3（`feat/m6-serve`）: `vidcut serve`・ビルド済み frontend の配信・OpenAPI からの型生成（openapi-typescript）・手動確認（`~/VidCut/` の写しで行う）
- [ ] 間の調整（M8 に追加済み）: 文の終わりのあとの間を長くする。一通り仕上げてから、編集画面のプレビューで聞きながら決める（ユーザー決定、2026-10-03）

## 決定事項

| #   | 決定内容                                                                      | 理由                                                           | ADR               |
| --- | ----------------------------------------------------------------------------- | -------------------------------------------------------------- | ----------------- |
| 1   | 仕上げは Premiere Pro。Premiere XML（xmeml）の書き出しを優先し、MP4 は補助    | ユーザー決定（kickoff）                                        | —                 |
| 2   | テロップは MVP から外すが、データモデルは文字単位のタイミングを前提に設計する | ユーザー決定（kickoff）                                        | —                 |
| 3   | 「カット」の合図は使わない                                                    | 撮影済み素材が多く、合図があってもカット開始点が明確にならない | —                 |
| 4   | 言い直しの判定は `claude -p`（サブスクの範囲内）                              | 費用を避ける                                                   | —                 |
| 5 | Python（パイプライン + API）+ TypeScript（UI）。Tauri 化は保留 | 音声 ML は Python、編集 UI は Web が最適 | ADR-001 |
| 6 | MVP は編集画面（3 ペイン・テキスト編集）まで含める | ユーザー決定（2026-10-03） | — |
| 7 | 正解データとの一致率は開発上の暫定指標。合格判定は実際の撮影素材を使い人が行う | ユーザー決定（2026-10-03） | — |
| 8 | MP4 の直接書き出し（US-09）を MVP に含める | ユーザー決定（2026-10-03） | — |
| 10 | まとめて解析（US-10）を MVP に含める | ユーザー決定（2026-10-03） | — |
| 11 | 一括解析は画面から投入・進捗確認できる形にする（コマンドラインからも可） | ユーザー決定（2026-10-03） | — |
| 12 | 別ファイルへの撮り直しがあるため、編集単位を「レクチャー（順序付きの複数録画ファイル）」とし、言い直し判定はレクチャー全体で行う | ユーザー回答（2026-10-03） | — |
| 13 | ワークスペースは `~/VidCut/`。Premiere のシーケンス設定は暫定で元素材の解像度・60fps | ユーザー合意（2026-10-03） | ADR-004 |
| 14 | 中間素材とシーケンスは 60fps。Premiere XML は中間素材を参照する（元素材の直接参照は大きくずれる） | ユーザー決定・S-1 の結果（2026-10-03） | ADR-002 |
| 15 | 文字起こしは mlx-whisper large-v3-turbo + WhisperX の位置合わせ | S-2・S-3 の結果 | ADR-003 |
| 16 | M6 は 3 本の PR に分け、ブランチを積み上げる（下ごしらえ → FastAPI → serve と型生成） | ユーザー承認（2026-10-03） | — |
| 17 | proxy 動画だけ、トークンを `?token=` のクエリで受ける（`<video>` はヘッダーを付けられない）。アクセスログにクエリを出さない | ユーザー決定（2026-10-03） | Design Doc 3-5-1 |
| 18 | M6 の設計判断: SQLite の接続はリクエストごと、失敗は種別（`error_code`）で返す、再解析は API のみ、レクチャー名は NFC + 見えない文字の除去、判定結果と編集状態は 1 トランザクション、まとめる・解除で編集状態を引き継ぐ | ユーザー承認（2026-10-03） | Design Doc 3-5-2 |
| 9 | 合格ライン: 実素材 3 本、誤削除 1 本あたり 2 件以下、作業時間は手作業の半分以下。暫定指標: 適合率 ≥ 90%・再現率 ≥ 80%・6 分素材の解析 ≤ 5 分 | ユーザー合意（2026-10-03） | — |

## ブロッカー

_なし_

## メモ

- 要件の入力: [docs/references/kickoff.md](./docs/references/kickoff.md)。プロトタイプと正解データ: `docs/references/prototype/`
- `claude -p` は再ログイン済み。リポジトリ内で呼ぶと開発用設定が読み込まれるので、中立なディレクトリから呼ぶ（FRIC-002）
- deny ルールの記法を修正済み（FRIC-001）。master へは claude-config-master#2 で反映済み
- スパイク S-4 完了: 判定は正解データと 3 回とも完全一致
- 検証素材にはフィラーがない（ユーザー確認）。フィラー検出の精度は未検証（Design Doc D-5）
- スパイクの素材と XML は `~/VidCut/spikes/s1/` にある
- 開発の流れ: main からマイルストーンごとにブランチ（`feat/m2-adapters` など）→ review-loop（`.claude/skills/review-loop/SKILL.md`）→ PR → ユーザーがマージ
- master（claude-config-master）への PR #2（deny ルール）・#3（フックのサブディレクトリ対応）はマージ済み。#4（FRIC-004）もマージ済み
- セキュリティレビューの未対応: settings.json の `Read(~/.ssh/*)` 等の `**` 化（ユーザー判断）、フックの `npx --no-install` 化（PR #2 の説明に記載）
- 実素材は音声が映像より 51ms 遅れて始まる。解析用の wav は `aresample=first_pts=0` で先頭を埋めてタイムラインにそろえている（M2 で発見、回帰テストあり）
- 中間素材の音声の時刻（M5 で調査。ADR-002）: 元素材のエディットリストは「51.25ms の空白 + 先頭 2,112 サンプルを飛ばす」、中間素材は「7ms の空白 + 先頭から再生」。
  ffmpeg で読むと両者は 0.25ms で一致する。Premiere でも音ズレはなかった（ユーザー確認）。中間素材の音声はコピーのままでよい
- 書き出しの CLI はない（計画外）。検証素材の書き出しは、`build_app` → `app.exports.request(...)` → `app.worker().run_until_idle()` の使い捨てスクリプトで行った。
  CLI にするなら `vidcut export <レクチャーの題名または id> [--format premiere|mp4|both] [--wait]`（`eval judge --lecture` と同じ指定の仕方）を提案済み
- 検証素材は `~/VidCut/` に登録済み（レクチャー `s05-12sample`）。書き出しの実測: Premiere XML は 1 秒未満、MP4 は約 2 分半（39 区間・172 秒・98MB）。MP4 の音声は全 39 区間で元素材と 0.25ms 以内で一致（相互相関で計測）
- 書き出し（M5）の制限: 音声はステレオ前提。レクチャー内で解像度や音声形式が違う録画を混ぜた MP4 は失敗する。同じ名前のレクチャーは同じ `exports/<名前>/` に上書きする。
  MP4 のつなぎ目にフェードはない（プロトタイプは 30ms のフェードを付けていた。必要なら Premiere XML との一致をどうするかと合わせて決める）
- 解析の段 5（無音）を更新した（M5。無音を録画の終わりまで延ばす）。M5 より前に解析した録画は、解析し直すと無音の段から作り直される
- 実素材での M2 の実測: probe 0.1 秒、解析用 wav 0.4 秒、ピーク値 0.2 秒、proxy 38 秒、中間素材 296 秒（196MB）。proxy の 38 秒は解析時間の目標（5 分）に含まれる
- M2 のセキュリティレビューの LOW: ffmpeg のタイムアウトは M3 で対応済み（録画の長さに応じた上限）。ジョブのエラー文に絶対パス（ユーザー名）が入る → M6 PR 1 で種別（`Job.error_code`）を記録するようにした。PR 2 の API は種別と定型文だけを返すこと（生の `Job.error` と `ImportFailure.message` は返さない）
- ML の依存は `uv sync --extra ml` で導入済み（`uv run` では消えない）。実物のモデルのテストは `uv run pytest -m ml`
- 検証素材のチャンク 32 の幻聴「ご視聴ありがとうございました。」は、位置合わせの失敗でトークンが 0 個になり判定に届いていなかった。M4 で文字を残すように直し、判定が `noise` として削除することを確認した
- M4 より前に解析した録画ファイルは、解析し直すと位置合わせの段から作り直される（段のキーを上げた）。解析し直す手段は `LectureService.reanalyze`（M6 PR 1）。API は PR 2 の `POST /api/lectures/{id}/reanalyze`
- `claude -p` は `<ワークスペース>/judge/` から `--tools ""` と `--safe-mode` を付けて呼ぶ（FRIC-002 は解消）。未ログインだと判定ジョブだけが失敗し、エラーに `/login` の案内が出る
- 判定の評価: `uv run vidcut eval judge --chunks … --truth …`（プロトタイプのチャンク）または `--lecture <題名>`（解析済みのレクチャー）。1 回約 15 秒
- 複数ファイルのレクチャーと 300 チャンク超の窓分割は、検証素材を人工的に分けた確認だけ（結果は変わらず）。実素材では M8 で確かめる
- M3 のセキュリティレビューの LOW: ジョブのエラー文と CLI の出力に ffmpeg の stderr や絶対パスが入る → 上と同じく種別で返す（CLI は自分の端末なので生の文を出す）。wav は一括で読み込む（2 時間で約 230MB）
- コマンドを `| tail` でつなぐと失敗が隠れる。テストとコミットを連結するときは `set -o pipefail` を付ける
- quality-gate フックは `.md` の編集時にも prettier を走らせ、表を整形し直す。frontend のファイルは frontend/biome.json の Biome で整形する（FRIC-003 で修正済み、master へは PR #3）
- M6 PR 1 で用意した、PR 2 の API が使うもの（`bootstrap.App`）: `lecture_service`（merge / reorder / split / reanalyze）、`edits`（`EditService.save`）、`lecture_views`（`LectureQuery.summaries` / `detail`）、`exports.request`、`imports.import_paths`、`queue`（一覧・retry）。
  入力の誤りは `InvalidInputError`（422 にする）、見つからないものは `NotFoundError`、版の食い違いは `VersionConflictError`（409 にする）
- 複数のリポジトリにまたがる保存は `Atomic`（ports）で囲む。SQLite の `transaction()` は、既にトランザクションの中ならそれに加わる
- M6 PR 2 で決めること: `build_app` はワーカー用にすべてを組み立てる（ML・`claude` を含む）。API はリクエストごとに接続を開くので、API 用の軽い組み立て（リポジトリと services だけ）を `bootstrap.py` に分ける
- M6 PR 1 の制限: まとめる・解除のとき、元のレクチャーを処理中のジョブは失敗として残る。`dropped_restored_ids` の通知を閉じる仕組みは M7 で決める。ffmpeg の一時ファイルは強制終了で残る（1 日以上前のものは、次に同じ生成物を作るときに消す）
- M6 PR 1 のセキュリティレビュー（WARNING で通過）から、PR 2 で必ず行うこと: 応答の型は許可リスト方式にし、生の `Job.error` と `ImportFailure.message` が出ないことをテストで固定する（一覧と詳細は `JobView` を返すようにした）。
  pydantic で件数（`lecture_ids`・`recording_ids`・`manual_cuts`・`restored_suggestion_ids`）、id の長さと文字種、題名の長さ（100 文字を超えたら拒否）、本文のサイズを制限する。
  例外の文（`str(e)`）は絶対パスを含みうるので、応答には定型文だけを入れる（symlink の拒否、壊れた JSON など）。500 の応答に例外文とスタックトレースを出さない
- M6 PR 2 の下調べ（プロジェクト外で確認）: fastapi 0.142 / starlette 1.7 / pydantic 2.13 / uvicorn 0.54。`FileResponse` は Range に対応（206 / 416）。厳格な型（`strict=True`・`extra="forbid"`）は期待どおり 422。
  本文サイズは `Content-Length` で先に弾く（読みながら数えると 400 になる）。JSON 以外の Content-Type は明示的に 415 にする。
  Starlette のテストクライアントは `httpx` ではなく `httpx2`（pydantic/httpx2）を推奨し、`httpx` だと非推奨の警告が出る → 承認済みの一覧（dev に httpx）と違うので、PR 2 の着手時にユーザーに確認する

