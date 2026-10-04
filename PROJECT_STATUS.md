# プロジェクト状態

> Claude Code が自律的に管理するファイル。タスク完了・フェーズ移行のたびに更新すること。
> セッション開始時は必ずこのファイルを読んで状態を復元すること。

## 現在のフェーズ

<!-- 選択肢: 議論中 | ドキュメント作成中 | 実装中 | レビュー中 | メンテナンス中 | 完了 -->

実装中

## 概要

vid-cut: Udemy 用の録画（mov）から無音・フィラー・言い直しを自動検出してカットし、Premiere XML で書き出すローカルアプリ。
PRD・Design Doc が承認済み。実装計画（M0〜M8）を承認。M0〜M6 と FRIC-004 の解消、M7 の PR 1（土台）・PR 2（素材一覧）・PR 3（編集状態と文字起こしの基本）は main にマージ済み（PR #1〜#14）。M7（frontend）を 7 本の PR に分けて実装中。PR 4（要確認・判定理由・通知。`feat/m7-transcript-review`）を、ユーザー不在の間に推奨案で実装した（画面の構成はユーザー確認待ち）。GitHub: kanpyou-maki/vid-cut（private）。

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
- [x] M6: API（services と保存まわり・FastAPI とローカル API の防御・`vidcut serve`・frontend の配信・OpenAPI からの型生成。テスト 1,015 件 / カバレッジ 99%。review-loop 全通過。PR #9〜#11）。`~/VidCut/` の写しで手動確認し、問題なし（ユーザー確認）— 2026-10-04

## 進行中

- [ ] [PLAN-20261003-mvp-implementation](./docs/exec-plans/active/PLAN-20261003-mvp-implementation.md)— M0〜M6 完了。M7 は PR 3（編集状態と文字起こしの基本。PR #14）までマージ済み。PR 4（`feat/m7-transcript-review`）は review-loop を通過し、PR [#15](https://github.com/kanpyou-maki/vid-cut/pull/15) のマージ待ち（画面の構成はユーザー確認待ち）

## 次にやること

- [ ] M7 の PR 4 の確認（ユーザー）: 画面の構成（Design Doc 3-6 の「要確認・判定理由・通知」。不在の間に推奨案で実装した。PR の説明の先頭に、選んだ内容と代替案がある）と、
      手動確認（`frontend/README.md` の「手で確かめる（M7 の PR 4: 要確認・判定理由・通知）」）。問題なければマージ
- [ ] M7: frontend。PR 4 のあとは PR 5（`feat/m7-preview`: プレビュー）。ユーザー不在の間は、PR 4 の上に積んで進める（PR 4 に直しが入ったら、PR 5 も直す。今夜は PR 5 まで。PR 6 と PR 7 は、ユーザーが戻ってから）。PR の分け方と順番は実装計画の M7（PR 1 土台 → 2 素材一覧 → 3 編集状態と文字起こしの基本 → 4 要確認・判定理由・通知 → 5 プレビュー → 6 波形 → 7 書き出し）
- [ ] 画面の実装で守ること: トークンは meta 要素から読んでヘッダーに付ける（`localStorage`・URL・ログに残さない）、`dangerouslySetInnerHTML` を使わない、外部の CDN・フォント・画像を使わない。
      波形の部品を入れたあと（PR 6）、CSP の違反がコンソールに出ないかを確かめ、`style-src 'unsafe-inline'` を外せるか試す
- [ ] 間の調整（M8 に追加済み）: 文の終わりのあとの間を長くする。一通り仕上げてから、編集画面のプレビューで聞きながら決める（ユーザー決定、2026-10-03）

## 決定事項

| #   | 決定内容                                                                                                                                                                                                                | 理由                                                           | ADR                       |
| --- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------- | ------------------------- |
| 1   | 仕上げは Premiere Pro。Premiere XML（xmeml）の書き出しを優先し、MP4 は補助                                                                                                                                              | ユーザー決定（kickoff）                                        | —                         |
| 2   | テロップは MVP から外すが、データモデルは文字単位のタイミングを前提に設計する                                                                                                                                           | ユーザー決定（kickoff）                                        | —                         |
| 3   | 「カット」の合図は使わない                                                                                                                                                                                              | 撮影済み素材が多く、合図があってもカット開始点が明確にならない | —                         |
| 4   | 言い直しの判定は `claude -p`（サブスクの範囲内）                                                                                                                                                                        | 費用を避ける                                                   | —                         |
| 5   | Python（パイプライン + API）+ TypeScript（UI）。Tauri 化は保留                                                                                                                                                          | 音声 ML は Python、編集 UI は Web が最適                       | ADR-001                   |
| 6   | MVP は編集画面（3 ペイン・テキスト編集）まで含める                                                                                                                                                                      | ユーザー決定（2026-10-03）                                     | —                         |
| 7   | 正解データとの一致率は開発上の暫定指標。合格判定は実際の撮影素材を使い人が行う                                                                                                                                          | ユーザー決定（2026-10-03）                                     | —                         |
| 8   | MP4 の直接書き出し（US-09）を MVP に含める                                                                                                                                                                              | ユーザー決定（2026-10-03）                                     | —                         |
| 10  | まとめて解析（US-10）を MVP に含める                                                                                                                                                                                    | ユーザー決定（2026-10-03）                                     | —                         |
| 11  | 一括解析は画面から投入・進捗確認できる形にする（コマンドラインからも可）                                                                                                                                                | ユーザー決定（2026-10-03）                                     | —                         |
| 12  | 別ファイルへの撮り直しがあるため、編集単位を「レクチャー（順序付きの複数録画ファイル）」とし、言い直し判定はレクチャー全体で行う                                                                                        | ユーザー回答（2026-10-03）                                     | —                         |
| 13  | ワークスペースは `~/VidCut/`。Premiere のシーケンス設定は暫定で元素材の解像度・60fps                                                                                                                                    | ユーザー合意（2026-10-03）                                     | ADR-004                   |
| 14  | 中間素材とシーケンスは 60fps。Premiere XML は中間素材を参照する（元素材の直接参照は大きくずれる）                                                                                                                       | ユーザー決定・S-1 の結果（2026-10-03）                         | ADR-002                   |
| 15  | 文字起こしは mlx-whisper large-v3-turbo + WhisperX の位置合わせ                                                                                                                                                         | S-2・S-3 の結果                                                | ADR-003                   |
| 16  | M6 は 3 本の PR に分け、ブランチを積み上げる（下ごしらえ → FastAPI → serve と型生成）                                                                                                                                   | ユーザー承認（2026-10-03）                                     | —                         |
| 17  | proxy 動画だけ、トークンを `?token=` のクエリで受ける（`<video>` はヘッダーを付けられない）。アクセスログは出さない                                                                                                     | ユーザー決定（2026-10-03）                                     | ADR-005・Design Doc 3-5-1 |
| 18  | M6 の設計判断: SQLite の接続はリクエストごと、失敗は種別（`error_code`）で返す、再解析は API のみ、レクチャー名は NFC + 見えない文字の除去、判定結果と編集状態は 1 トランザクション、まとめる・解除で編集状態を引き継ぐ | ユーザー承認（2026-10-03）                                     | ADR-005・Design Doc 3-5-2 |
| 19  | テスト用の依存は `httpx2` を使う（当初は `httpx`。Starlette が `httpx2` を推奨するため）                                                                                                                                | ユーザー決定（2026-10-03）                                     | —                         |
| 20  | `openapi-typescript` 7 には、`overrides` でプロジェクトの TypeScript 6 を使わせる                                                                                                                                       | ユーザー承認（2026-10-03）                                     | —                         |
| 21  | ADR-005（API の接続・まとめて確定する保存・トークン）を承認                                                                                                                                                             | ユーザー承認（2026-10-03）                                     | ADR-005                   |
| 22  | M7 は 7 本の PR に分ける（土台 → 素材一覧 → 編集状態 → 要確認・判定理由・通知 → プレビュー → 波形 → 書き出し）                                                                                                          | ユーザー承認（2026-10-04）                                     | —                         |
| 23  | 開発中のトークンは Vite のプラグインが埋め込む。backend は、ビルドの案内のページ（503）にもトークンを入れる                                                                                                             | ユーザー決定（2026-10-04）                                     | ADR-006                   |
| 24  | 書き出し先はレクチャーの詳細に足す（フォルダ、形式ごとのパスと最後に書き出した日時）。Finder で開く API（`POST /api/lectures/{id}/exports/reveal`）を足す                                                               | ユーザー決定（2026-10-04）                                     | Design Doc 3-5            |
| 25  | `dropped_restored_ids` の通知は、サーバー側で閉じる API を足す（画面が表示した id だけを消す）。通知は件数だけ                                                                                                          | ユーザー決定（2026-10-04）                                     | Design Doc 3-5            |
| 26  | frontend に足す依存は `openapi-fetch` と `wavesurfer.js`（最新の安定版。8 系）だけ。ルーティング・データ取得・UI 部品のライブラリは入れない                                                                             | ユーザー承認（2026-10-04）                                     | ADR-006                   |
| 9   | 合格ライン: 実素材 3 本、誤削除 1 本あたり 2 件以下、作業時間は手作業の半分以下。暫定指標: 適合率 ≥ 90%・再現率 ≥ 80%・6 分素材の解析 ≤ 5 分                                                                            | ユーザー合意（2026-10-03）                                     | —                         |

## ブロッカー

_なし_

## メモ

### 進め方

- 開発の流れ: main からマイルストーンごとにブランチ → review-loop（`.claude/skills/review-loop/SKILL.md`）→ PR → ユーザーがマージ。M6 は 3 本の PR を積み上げている（決定事項 16）
- コマンドを `| tail` でつなぐと失敗が隠れる。テストとコミットを連結するときは `set -o pipefail` を付ける
- quality-gate フックは `.md` の編集時にも prettier を走らせ、表を整形し直す。frontend のファイルは frontend/biome.json の Biome で整形する（FRIC-003）
- ML の依存は `uv sync --extra ml` で導入済み（`uv run` では消えない）。実物のモデルのテストは `uv run pytest -m ml`
- 要件の入力: [docs/references/kickoff.md](./docs/references/kickoff.md)。プロトタイプと正解データ: `docs/references/prototype/`。スパイクの素材と XML は `~/VidCut/spikes/s1/`
- ハーネス: deny ルール（FRIC-001）・フックのサブディレクトリ対応（FRIC-003）・整形のルール（FRIC-004）は master に反映済み。
  セキュリティレビューの未対応: settings.json の `Read(~/.ssh/*)` 等の `**` 化（ユーザー判断）、フックの `npx --no-install` 化

### M6（API）で作ったもの（M7 が使う）

- PR 1（`feat/m6-api`、PR #9）: services と保存まわり。PR 2（`feat/m6-api-http`、PR #10）: FastAPI のアプリ・防御・入力の上限・各エンドポイント。PR 3（`feat/m6-serve`、PR #11）: `vidcut serve`・frontend の配信・型生成。設計と決まりは Design Doc 3-5・3-5-1・3-5-2 と ADR-005
- 構成: `api/app.py` の `create_app(api, settings)`、`api/security.py`（Host・Origin・トークン・本文）、`api/inputs.py`（入力の上限）・`api/outputs.py`（出力の許可リスト）・`api/presenters.py`（出力への変換）、`api/errors.py`・`api/messages.py`（定型文）、`api/routes/`。
  `bootstrap.build_api(workspace)` が起動時に 1 回スキーマを移行し、`Api.services()` がリクエストごとに接続を開く。`ApiServices` は `imports`・`lecture_service`・`lecture_views`・`edits`・`exports`・`jobs`（`JobControl`）・`artifacts`（`RecordingArtifacts`）を持つ。API は ML も `claude` も組み立てない（判定の登録は `JudgeRequests`）
- 守ること: 応答には種別（`error_code`）と定型文だけを入れる（生の `Job.error`・`ImportFailure.message`・例外の文は入れない）。`InvalidInputError` の文だけはそのまま画面に出るので、絶対パスやほかの例外の文を入れない。
  複数のリポジトリにまたがる保存は `Atomic`（ports）で囲む
- 実物の uvicorn を一時ワークスペースで確認済み（PR 2）: 並行の読み取り 200 件が成功、同じ版での同時保存は 1 件だけ成功して残りは 409、トークンなしは 401、別の Host は 403
- テスト用の依存は `httpx2`（pydantic/httpx2。Starlette 1.7 のテストクライアントが推奨。決定事項 19）。当初の `httpx` から PR 3 で替え、非推奨の警告はなくなった
- `uv add` / `uv remove` は、ML の追加依存（`--extra ml`）を外して環境を同期し直す。numpy も外れて backend の読み込みが失敗するので、依存を変えたあとは `uv sync --extra ml` を実行する（M6 で発生）
- PR 3（`feat/m6-serve`）: `serve.py`（127.0.0.1 に固定、トークンは起動ごとに作って HTML の `<meta name="vidcut-token">` に埋め込む、アクセスログなし、worker の子プロセスの起動と停止）、
  `api/frontend.py`（ビルドの出力の配信）、`api/headers.py`（CSP などのヘッダー）、`vidcut openapi` と `npm --prefix frontend run gen:api`（型は `frontend/src/api/generated/`）、
  実物のサーバーでの結合テスト（`tests/test_serve_integration.py`）、ADR-005（承認済み）。`pip-audit` と `npm audit` は既知の脆弱性なし（2026-10-03）
- 結合テストで見つけた不具合（修正済み）: SIGTERM で止めると、uvicorn がシグナルを送り直してプロセスがその場で終わり、worker が残った → SIGTERM を KeyboardInterrupt に変えてから起動する
- `openapi-typescript` 7.13 は peer 依存が TypeScript 5 で、このプロジェクトの TypeScript 6 と衝突する → `frontend/package.json` の `overrides` でプロジェクトの TypeScript を使わせている（決定事項 20。生成と型チェックは通る）
- `vidcut serve` を SIGKILL で止めても worker は残らない: serve が worker に自分のプロセス番号を渡し（`--parent-pid`）、worker は親が変わったら自分で止まる（処理中のジョブがあれば、それが終わってから）。
  実物のサーバーを起動するテスト（`tests/test_serve_integration.py`）は、後始末でプロセスグループごと止める。開発中に worker が残っていないかは `pgrep -fl "vidcut.cli"` で確かめられる
- PR 2 のセキュリティレビューで受け入れたもの: ワークスペース `~/VidCut/` がホーム配下にあり、生成物（`proxy.mp4` など）を録画として取り込める（事故の二重解析はありうる）。フォルダの取り込みは件数を打ち切らない（巨大なフォルダでは時間がかかる）
- 制限: まとめる・解除のとき、元のレクチャーを処理中のジョブは失敗として残る。ffmpeg の一時ファイルは強制終了で残る（1 日以上前のものは、次に同じ生成物を作るときに消す）
- M7 で API に足すもの: 書き出し先のパスの表示と Finder で開く API（PR 7。決定事項 24）、`dropped_restored_ids` の通知を閉じる API（PR 4。決定事項 25）

### M7（frontend）の現状

- PR 1（`feat/m7-foundation`、PR #12）: 土台。backend は、ビルドの案内のページ（503）にもトークンを埋め込む。frontend は `openapi-fetch` を追加し、
  `src/api/`（`Api`・トークン・失敗の種類）、`src/shared/`（画面の切り替え・ポーリング）、`src/app/`（画面の枠）、`src/library/`（名前と状態の一覧まで）、`src/editor/`（準備中の表示だけ）、
  `vite-plugins/devToken.ts`（開発中のトークン）。frontend のテスト 105 件 / カバレッジ 99%
- 実物の backend と Vite を一時ワークスペースで起動して確認済み: 開発用の HTML に backend と同じトークンが入る、Vite 経由の API が通る、トークンなしは 401、
  ほかのオリジンには CORS のヘッダーを返さない、ビルドの出力と各プロセスの出力にトークンが出ない、本番の画面にインラインのスクリプト・スタイルがない
- 画面の作り方: 画面は `Api`（`src/api/client.ts`）のメソッドだけを使い、テストでは `src/test/fakeApi.ts` の偽物に差し替える。画面に出す失敗の文は `errorMessage` を通す。
  API クライアントのテストは Node の環境で動かす（jsdom の `AbortSignal` は Node の `Request` に渡せない）。`openapi-fetch` には `baseUrl` に画面のオリジンを渡す（相対パスだと Node で `Request` を作れない）
- 手動確認の手順: `frontend/README.md` の「手で確かめる（M7 の PR 1: 土台）」。PR 2・PR 3 の手順も同じファイルにある
- PR 2（`feat/m7-library`）: 素材一覧。画面の構成はユーザー承認（2026-10-04。Design Doc 3-6 の「素材一覧」）。backend の変更なし。
  `Api` に `listDirectory`・`importPaths`・`mergeLectures`・`reorderLecture`・`splitLecture`・`retryJob` を足した。`usePolling` は `refresh`（すぐに読み直す）を返す。
  ダイアログは `src/shared/Modal.tsx`（`dialog` 要素の `showModal`）。jsdom は `showModal` を持たないので、`src/test/setup.ts` に代わりの実装がある。閉じるときは描くのをやめ、フォーカスを開く前の要素へ戻す。frontend のテスト 232 件 / カバレッジ 99%（分岐 96%）
- PR 2 で確認済み（一時ワークスペース。実物の backend）: 足した `Api` のメソッドが通る（日本語と空白を含むパス、本文のない POST、422・404 の文）。
  ヘッドレスの Chrome（CDP で操作）で、投入 → 失敗と再実行 → まとめる → 並べ替え → 解除が動き、コンソールの失敗と CSP の違反がない。
  実物の解析で、元のファイルを消す → 失敗（`source_missing`）→ 作り直す → 再実行 → 編集待ち、まで進む
- 画面を自分で確かめる方法: Chrome を `--headless=new --remote-debugging-port` で起動し、Node の `WebSocket` から CDP（`Runtime.evaluate`・`Page.captureScreenshot`）で操作する（依存は増えない）。
  `/api/fs` は隠しフォルダを扱わないので、素材の一時フォルダはホームの直下に作って最後に消す。ビルドは `npx vite build --outDir <一時フォルダ>` と `VIDCUT_FRONTEND_DIST` で、`frontend/dist` を書き換えずに済む
- PR 3（`feat/m7-editor-state`）: 編集画面の骨組みと編集状態。画面の構成はユーザー承認（2026-10-04。Design Doc 3-6 の「編集画面の骨組みと編集状態」）。backend の変更なし。
  `Api` に `getLecture`・`saveEdits` を足した。`src/editor/` は、待ち受け（`LectureGate`。編集できる状態になるまで `usePolling` で読み直し、なったら読み直しをやめる）と
  編集（`EditorWorkspace` と `useEditing`。`useReducer` + 履歴、自動保存、文字起こしの操作）に分かれる。読み込み直し（409 のあと）は、待ち受けからやり直して編集の部品ごと作り直す。
  編集状態は不変のオブジェクトで、自動保存（`autosaver.ts`。React の外で持つ）は「保存済みと同じオブジェクトか」で未保存を判断する（undo で保存済みの内容に戻れば、保存しない）。
  状態・失敗・時間の文は `src/shared/lectureStatus.ts` に移し、素材一覧と共用する
- PR 3 で確認済み（`~/VidCut` の DB と解析結果の JSON だけを写した一時ワークスペース。実物の backend を `--no-worker` で起動、ヘッドレスの Chrome）:
  マウスのドラッグで選択 → Delete → 約 1 秒後に保存（削除区間は最初のトークンの開始〜最後のトークンの終了）、⌘Z / ⇧⌘Z とボタン、「削除」ボタン（押しても選択が外れない）、
  クリックと Enter での復活、読み込み直しても続きから、別の保存を挟んだあとの 409 のダイアログ（Esc で閉じない）と読み込み直し、未保存のまま素材一覧へ移っても保存される、
  判定を待つ間の読み取り専用、幅が狭いときの縦積み、暗い配色。コンソールの失敗と CSP の違反なし（わざと起こした 404・409 の記録だけ）。frontend のテスト 378 件 / カバレッジ 99%（分岐 96%）
- PR 3 の review-loop: Stage 0（self）・Stage 1（arch / style / test）・Stage 2（security / docs）すべて PASS。提案を受けて、トークンの通し番号を画面に並ぶ順に振るようにした
  （削除の判定は、中央の時刻の順の一覧 `byCenter` で行う。チャンクのトークンが時刻の上で入り交じっていても、選択範囲と通し番号がずれない）。
  セキュリティの LOW（情報）: ジョブの `error_message` は backend の定型文をそのまま出す（素材一覧と同じ）。タブを閉じるときは確認を出すだけで、保存は走らない（承認済みの方針）
- PR 4（`feat/m7-transcript-review`）: 要確認・判定理由・通知。ユーザー不在（2026-10-04 の夜）の間に、画面の構成を推奨案で決めて実装した（**ユーザー確認待ち**。Design Doc 3-6）。
  backend に `POST /api/lectures/{id}/dropped-restorations/dismiss` を足した（`EditService.dismiss_dropped_restorations` → `JudgementRepository.dismiss_dropped`。記録の列だけを 1 トランザクションで書き換える）。
  frontend は、`Api.dismissDroppedRestorations`、要確認の印（`transcript.ts` の `lowConfidence`・`unrecognized`・`reviewTargets`）と移動（`useReviewNavigation.ts`。N / Shift+N）、
  判定理由（`CutReason.tsx`。文字起こしを描き直さないよう、カーソルの出入りを `document` で受ける）、戻した候補の表示と「削除に戻す」（`edits.ts` の `tokenRestorations`・`reapplySuggestion`）、通知（`DroppedNotice.tsx`）。
  自動の候補の説明は理由の表示に移したので、削除済みの候補の `title` はなくなった（手動の削除には残る）
- PR 4 で確認済み（PR 3 と同じ一時ワークスペース。引き継げなかった候補 2 件と、未認識の発話 1 件を足した）: 通知の件数と「閉じる」（サーバーの記録からも消える）、
  要確認の数・波線・未認識の発話の行、ボタンと N / Shift+N での移動（選択されて見える位置に出る）、カーソルを合わせると理由がすぐ下に出る、理由の上へカーソルを移しても消えない、
  「言い直し先へ移動」で段落が出て目印が付く、クリックで「戻し済み」になり理由も切り替わる、もう一度クリックで削除に戻って保存される。PR 3 の項目と合わせて 44 項目 OK。frontend のテスト 423 件 / カバレッジ 99%（分岐 96%）、backend 1,029 件
- PR 4 の review-loop: Stage 0・Stage 1・Stage 2 すべて PASS（docs-reviewer は 1 回 BLOCK: `frontend/README.md` の PR 3 の手順に、PR 4 で変わった表示が古いまま残っていた → 修正して PASS）。
  挙動を変えたら、前の PR の手動確認の手順も、いまの挙動に合わせて直す。セキュリティの指摘なし
- PR 4 で踏んだこと: 要素ごとの `mouseenter` / `mouseleave`（React の `onMouseEnter` と、要素に直接付けたリスナー）を混ぜると、「対象から出た」と「理由に入った」の順序が食い違い、理由の上に移ったときに消える
  （jsdom のテストでは見つからず、実物の Chrome で見つけた。カーソルの出入りは `document` の `mouseover` 1 か所で受ける。再発を防ぐテストを足し、旧い受け方に戻すと落ちることを確かめた）。段落に `tabIndex={-1}` を付けると、クリックでフォーカスの枠が付く（移動先の目印は、クラスの付け外しによる一時的な背景色にした）
- 編集画面で踏んだこと: `Transcript.tsx` と `transcript.ts` を同じフォルダに置くと、macOS（大文字と小文字を区別しない）で読み込みを取り違える（部品は `TranscriptView.tsx` にした）。
  選択範囲とトークンの重なりは、トークンの要素ではなく中の文字（テキストノード）の範囲で比べる（要素で比べると、文字の境目で始まる選択が隣のトークンにも重なって見える）。
  画面のテストでタイマーを偽物にするときは `vi.useFakeTimers({ shouldAdvanceTime: true })` を使い、描いた直後は `advance(0)` で effect を流してからキーを送る（`src/test/editorPage.tsx`）
- 編集画面の残り・制限: 無音の候補はトークンを持たないので文字起こしに出ず、波形（PR 6）まで画面から戻せない。編集できる状態になったあとは読み直さない（別のタブでの並べ替えや判定のやり直しは、版が変わらなければ気づかない。PR 4 の通知は、開いたときの分だけを出す。開いている間の変化を知らせる仕組みは、まだない）。
  解析結果が読めない録画ファイルは、解析し直す必要があることを伝えるだけ（再解析は API のみ。決定事項 18）。サーバーを起動し直すとトークンが変わるので、未保存の編集は保存できず、読み込み直すと失われる。
  編集してから 1 秒以内に素材一覧へ戻り、すぐ同じレクチャーを開き直すと、離れるときの保存と読み込みが前後して、次の編集で 409 のダイアログが出ることがある（読み込み直せば続けられる）。
  編集のたびに文字起こし全体を描き直す（検証素材の 1,505 トークンでは問題なし。長い素材で重ければ、段落ごとに描き直しを抑える）
- 素材一覧の残り: 判定の進捗（%）は出していない（窓が 1 つだと 0% のまま）。処理中のボタンは `disabled` にするので、キーボードで ↑ ↓ を続けて押すとフォーカスが外れることがある

### 素材と解析・判定・書き出しの知見

- 検証素材は `~/VidCut/` に登録済み（レクチャー `s05-12sample`）。フィラーがない（ユーザー確認）ので、フィラー検出の精度は未検証（Design Doc D-5）
- 実素材は音声が映像より 51ms 遅れて始まる。解析用の wav は `aresample=first_pts=0` で先頭を埋めてタイムラインにそろえている（M2 で発見、回帰テストあり）
- 中間素材の音声の時刻（M5 で調査。ADR-002）: ffmpeg で読むと元素材と 0.25ms で一致する。Premiere でも音ズレはなかった（ユーザー確認）。中間素材の音声はコピーのままでよい
- 実測: probe 0.1 秒、解析用 wav 0.4 秒、ピーク値 0.2 秒、proxy 38 秒、中間素材 296 秒（196MB）。書き出しは Premiere XML が 1 秒未満、MP4 が約 2 分半（39 区間・172 秒・98MB）
- 登録済みの録画は、解析し直すと古い段から作り直される（M4 で位置合わせ、M5 で無音の段を更新した）。解析し直す手段は `POST /api/lectures/{id}/reanalyze`（`LectureService.reanalyze`）
- `claude -p` は `<ワークスペース>/judge/` から `--tools ""` と `--safe-mode` を付けて呼ぶ（FRIC-002）。未ログインだと判定ジョブだけが失敗する（種別 `login_required`）
- 判定の評価: `uv run vidcut eval judge --chunks … --truth …`（プロトタイプのチャンク）または `--lecture <題名>`（解析済みのレクチャー）。1 回約 15 秒。検証素材では適合率・再現率とも 100%
- 複数ファイルのレクチャーと 300 チャンク超の窓分割は、検証素材を人工的に分けた確認だけ（結果は変わらず）。実素材では M8 で確かめる
- 書き出し（M5）の制限: 音声はステレオ前提。レクチャー内で解像度や音声形式が違う録画を混ぜた MP4 は失敗する。同じ名前のレクチャーは同じ `exports/<名前>/` に上書きする。
  MP4 のつなぎ目にフェードはない（プロトタイプは 30ms のフェードを付けていた。必要なら Premiere XML との一致をどうするかと合わせて決める）
- 書き出しの CLI はない。M6 の API（`POST /api/lectures/{id}/exports`）と M7 の画面から依頼する
- wav は一括で読み込む（2 時間で約 230MB）。CLI の出力には生のエラー文（ffmpeg の stderr や絶対パス）が出る（自分の端末なので許容）
