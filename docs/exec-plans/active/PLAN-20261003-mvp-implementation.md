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
- [x] 判定のやり直し時の、戻した候補（`restored_suggestion_ids`）の引き継ぎ

### M2: 外部ツールの土台（`feat/m2-adapters`）

- [x] ffmpeg adapter: probe、解析用の音声、proxy、波形のピーク値、中間素材（`tpad` で最後のフレームを延ばす）
- [x] 可変フレームレートの回帰テスト（S-1 の人工素材を lavfi で生成し、映像と音声の長さの一致、白枠とビープの同期を検証）
- [x] SQLite のリポジトリ（録画ファイル・レクチャー・編集状態・ジョブ）
- [x] ジョブ表と worker のループ（1 件ずつ、優先度、起動時の `running` → `queued` の復旧、失敗時の記録）
- 実装中に見つけたこと: 実素材は音声が 51ms 遅れて始まり、そのまま wav にすると時刻が 51ms ずれる。`aresample=first_pts=0` で先頭を無音で埋めてそろえ、回帰テストに含めた

### M3: 解析パイプライン（`feat/m3-analysis`）

- [x] 無音検出（Silero VAD + 音量）と発話チャンクへの分割
- [x] 文字起こし adapter（mlx-whisper large-v3-turbo、チャンクごと、ヒント文、`avg_logprob`）
- [x] 位置合わせ adapter（WhisperX、日本語、文字単位）
- [x] フィラー検出（辞書 + 前後の無音）と要確認の印（低確信度・未認識の発話）
- [x] `analyze_recording` ジョブ（段ごとの生成物のキャッシュと再開）、`make_mezzanine` ジョブ
- [x] CLI: `vidcut analyze <paths...> [--wait]`、`vidcut worker`
- [x] 手動確認: 検証素材で解析時間が 5 分以内（中間素材を除く）→ 2 分 29 秒（proxy 39 秒・文字起こし 76 秒・位置合わせ 31 秒）。中間素材は別ジョブで 4 分 53 秒
- 実装中に見つけたこと: VAD の発話区間を無音から単純に差し引くと、余韻と句の間の短い無音をまたぐ区間のせいでチャンクが 69 → 48 につながった。無音の内側に収まる VAD の区間だけを除くように直し、正解データの 69 チャンクと開始・終了とも 60ms 以内で一致した
- 残る課題: 解析ロジックを更新したとき、登録済みの録画ファイルを解析し直す手段がない（取り込みは「登録済み」で止まる）。M6 の API で再解析を用意する

### M4: 言い直しの判定（`feat/m4-judge`）

- [x] claude adapter（中立な作業ディレクトリ、引数リスト、タイムアウト、未ログインの検出）
- [x] 判定の指示文（プロトタイプを出発点に、ファイルの境目の扱いを追加）と出力スキーマの検証・再試行
- [x] チャンク数が多い場合の窓分割と統合
- [x] `judge_lecture` ジョブ（解析が終わったレクチャーに自動で積む。結果は SQLite の `judgements` 表。戻した候補の引き継ぎ）
- [x] `vidcut eval judge`: 正解データとの適合率・再現率（目標 ≥ 90% / ≥ 80%）→ 検証素材で 100% / 100%（プロトタイプのチャンク 1 回、実際の解析結果 3 回）
- 実装中に見つけたこと: 検証素材のチャンク 32 の幻聴「ご視聴ありがとうございました。」は、WhisperX が位置合わせに失敗して文字を 1 つも返さず、
  トークンが 0 個になって `analysis.json` から文字が消えていた（判定に届かない）。位置合わせが空のときは文字起こしの文字をチャンクに等分して残すように直し、
  判定で `noise` として削除されることを確認した
- 残る課題: 複数ファイルのレクチャーと 300 チャンクを超えるレクチャーは、検証素材を人工的に分けた確認しかできていない（どちらも結果は変わらなかった）。
  実際の素材では M8 の受け入れチェックで確かめる

### M5: 書き出し（`feat/m5-export`）

- [x] Premiere XML（xmeml v4、複数の録画ファイル、映像 1 + 音声 2 トラック、60fps）
- [x] MP4（中間素材から trim / concat、h264_videotoolbox）
- [x] `export_premiere` / `export_mp4` ジョブ（中間素材の完成を待つ）
- [x] 手動確認: 検証素材の書き出しを Premiere で読み込み、音ズレがないこと → ユーザーが確認（2026-10-03）。音ズレなし、カットも期待どおり
- 実装中に見つけたこと:
  - 解析用の音声は録画ファイルの長さ（probe の値）より 31ms 早く終わり、最後の無音と終わりの間の断片が 12 フレームのクリップとして書き出しの最後に残った。
    音声の終わりまで続く無音を録画ファイルの終わりまで延ばすように直した（解析の段 5。登録済みの録画は解析し直すと無音の段から作り直される）
  - 中間素材の音声の時刻を調べた（ADR-002「M5 の調査」）。ffmpeg で読むかぎり元素材と 0.25ms で一致する。Premiere でも音ズレはなかった
  - `concat` フィルタの出力はマイクロ秒単位の時刻になり、そのままでは固定フレームレートと認識されない。`fps` フィルタで直してから符号化する
- 残る課題: 書き出しの CLI はない（計画外。手動確認は使い捨てのスクリプトでジョブを積んで行った）。画面からの書き出しは M6 の API と M7 で用意する
- 手動確認で出た要望（ユーザー、2026-10-03）: セリフが詰まりすぎている。文の終わりのあとは間を持たせたい。一通り仕上げてから調整する（M8 に項目を追加）

### M6: API（3 本の PR に分ける。ユーザー承認、2026-10-03）

PR 1（`feat/m6-api`。API の下ごしらえ。新しい依存なし）:

- [x] M6 の決定を Design Doc に反映（3-5-2: 接続の持ち方・まとめて確定する保存・エラーの分類・再解析・レクチャー名・編集状態の引き継ぎ。3-5-1: proxy のトークン）
- [x] レクチャー名の正規化（NFC・見えない文字）、書き出し先のシンボリックリンクの拒否、ffmpeg の一時ファイル名の一意化（M5 のセキュリティレビューの LOW）
- [x] 失敗の種別（`error_code`）: worker が例外の型から分類して jobs 表に記録。取り込みの失敗も同じ種別
- [x] 判定結果と編集状態を 1 つのトランザクションで保存（`Atomic`）
- [x] `LectureService`（まとめる・並べ替え・解除・再解析。編集状態の引き継ぎ、判定ジョブの登録）
- [x] `EditService`（編集状態の検証と保存）、`LectureQuery`（一覧と状態、編集画面に必要なもの一式）

PR 2（`feat/m6-api-http`。fastapi・uvicorn・pydantic、dev に httpx を追加。httpx は PR 3 で httpx2 に替えた）:

- [x] FastAPI のアプリと `{success, data, error}` の形（待ち受けを 127.0.0.1 に限るのは PR 3 の `vidcut serve`）
- [x] ローカル API の防御（Design Doc 3-5-1: Host / Origin の検証、トークン、Content-Type、パスの正規化。トークンを起動ごとに作って HTML に埋め込むのは PR 3）
- [x] 入力の上限（M1 のセキュリティレビュー）: pydantic の厳格な型（StrictInt）、件数（manual_cuts・suggestions・silences）と JSON サイズ、文字列の長さ、時刻の上限（24 時間）。`reason` / `error` は画面でエスケープする
- [x] `/api/fs`（ホーム配下のみ、パスの検証）、`/api/imports`、`/api/lectures`（一覧・詳細・merge・order・split）、`/api/lectures/{id}/edits`（楽観的排他）、`/api/lectures/{id}/exports`、`/api/jobs`（一覧・retry）
- [x] `/api/recordings/{id}/proxy`（Range 対応。トークンは `?token=`）、`/peaks`
- [x] `/api/lectures/{id}/reanalyze`
- [x] SQLite の接続をリクエストごとに開く（Design Doc 3-5-2）。実物の uvicorn で、並行の読み取り 200 件と同時保存（1 件だけ成功、残りは 409）を確認

PR 3（`feat/m6-serve`。frontend の dev に openapi-typescript を追加）:

- [x] `vidcut serve`（API サーバー + worker の起動、127.0.0.1 のみ、起動ごとのトークン、アクセスログを出さない、ビルド済み frontend の配信と応答のヘッダー）
- [x] OpenAPI → `openapi-typescript` で frontend の型を生成（`vidcut openapi` と `npm run gen:api`。ずれはテストと lint で検出）
- [x] 実物のサーバーでの結合テスト（本文の長さの食い違い・重複したヘッダー・アクセスログ・止め方）、ADR-005
- [x] 手動確認: `~/VidCut/` の写しに対して `vidcut serve` を起動し、一覧・詳細・編集の保存・書き出し・再解析を確かめる → ユーザーが確認（2026-10-04）。問題なし

M6 で分かった制限:

- `vidcut serve` を SIGKILL で止めた場合、worker は親がいなくなったことに気づいて自分で止まる（処理中のジョブがあれば、それが終わってから）。SIGTERM と Ctrl+C では一緒に止まる
- 開発中（Vite の開発サーバー）のトークンの渡し方は、M7 の最初に決めた（Vite のプラグインが埋め込む。ADR-006）
- まとめる・解除のとき、元のレクチャーを処理中のジョブ（判定・書き出し）は、レクチャーがなくなったことで失敗として残る（待機中のものは消す）
- 引き継げなかった戻し候補の記録（`dropped_restored_ids`）は、次に判定をやり直すまで残る。画面で通知を閉じる API は、M7 の PR 4（`feat/m7-transcript-review`）で足す（Design Doc 3-5）
- ffmpeg の一時ファイル（`.<名前>.<8 桁>.partial.<拡張子>`）は、強制終了されると残る。1 日以上前のものは、次に同じ生成物を作るときに消す

### M7: frontend（7 本の PR に分ける。ユーザー承認、2026-10-04）

前の PR がマージ済みなら main から切り、まだなら積み上げる。1 本ごとに review-loop と、ブラウザでの手動確認（ユーザー）を行う。
決定は Design Doc 3-5・3-5-1・3-6 と [ADR-006](../../adr/ADR-006-frontend-foundation.md)。

PR 1（`feat/m7-foundation`。`openapi-fetch` を追加）:

- [x] M7 の決定を Design Doc と ADR-006 に反映（開発中のトークン・保存先の項目・通知を閉じる仕組み・依存）
- [x] backend: ビルドの案内のページ（503）にもトークンを埋め込む
- [x] 開発中のトークン: Vite のプラグイン（`vite-plugins/devToken.ts`）、開発サーバーの CORS を無効にする
- [x] API クライアント（トークンのヘッダー、`{success, data, error}` をほどく、失敗の種類）
- [x] 画面の切り替え（素材一覧 `/` と編集画面 `/lectures/{id}`）、ポーリング、画面の枠（レクチャーの名前と状態の一覧まで）
- [x] 手動確認（ユーザー）: `frontend/README.md` の「手で確かめる（M7 の PR 1: 土台）」→ ユーザーがマージ（PR #12、2026-10-04）

PR 2（`feat/m7-library`）:

- [x] 画面の構成の提案と承認（一覧の見せ方、投入ダイアログ、まとめるときの題名、並べ替えと解除、失敗と再実行。Design Doc 3-6）
- [x] API クライアントに `listDirectory`・`importPaths`・`mergeLectures`・`reorderLecture`・`splitLecture`・`retryJob` を足す（backend の変更なし）
- [x] 素材一覧: レクチャーの一覧と状態、投入ダイアログ（フォルダブラウザ）、まとめる・並べ替え・解除、失敗の再実行
- [x] 実物の backend と、ヘッドレスの Chrome での確認（投入 → 失敗と再実行 → まとめる → 並べ替え → 解除。コンソールの失敗なし）
- [x] review-loop（Stage 0〜2 すべて PASS）→ PR #13
- [x] 手動確認（ユーザー）: `frontend/README.md` の「手で確かめる（M7 の PR 2: 素材一覧）」→ ユーザーがマージ（PR #13、2026-10-04）

PR 3（`feat/m7-editor-state`）:

- [x] 画面の構成の提案と承認（3 ペインの配置、トークンの見せ方と色、選択 → 削除と復活、undo / redo のキー、自動保存の状態、409、解析・判定が済んでいないレクチャー。Design Doc 3-6）
- [x] API クライアントに `getLecture`・`saveEdits` を足す（backend の変更なし）
- [x] 編集画面の骨組み: 3 ペインのレイアウト、データ取得（編集できる状態になるまで 1 秒ごとに読み直す）
- [x] 編集状態: `useReducer` + 履歴による undo / redo、1 秒遅延の自動保存、409 の扱い
- [x] 文字起こしの基本: トークン表示、選択 → 削除、復活、種類ごとの色
- [x] 実物の backend と、ヘッドレスの Chrome での確認（選択 → 削除 → 保存 → undo / redo → 復活 → 読み込み直し → 409 → 読み取り専用。コンソールの失敗なし）
- [x] review-loop（Stage 0〜2 すべて PASS）→ PR #14
- [x] 手動確認（ユーザー）: `frontend/README.md` の「手で確かめる（M7 の PR 3: 編集状態と文字起こしの基本）」→ ユーザーがマージ（PR #14、2026-10-04）

PR 4（`feat/m7-transcript-review`）:

- [x] backend: 通知を閉じる API（`POST /api/lectures/{id}/dropped-restorations/dismiss`。画面が表示した id だけを消す）
- [x] 要確認の印（波線、未認識の発話の行）と移動（ボタン、N / Shift+N）
- [x] 判定理由の表示（カーソルを合わせた候補の近くに出す）と、言い直し先への移動。戻した候補の表示と、採否の切り替え
- [x] `dropped_restored_ids` の通知（件数と「閉じる」）
- [x] 実物の backend と、ヘッドレスの Chrome での確認（通知 → 要確認の移動 → 判定理由 → 言い直し先への移動 → 採否の切り替え。コンソールの失敗なし）
- [x] 画面の構成の確認（ユーザー。不在の間に推奨案で実装した。Design Doc 3-6 の「要確認・判定理由・通知」）
- [x] review-loop（Stage 0〜2 すべて PASS。docs-reviewer の BLOCK 1 回: README の PR 3 の手順が古いままだった → 修正して PASS）→ PR #15
- [x] 手動確認（ユーザー）: `frontend/README.md` の「手で確かめる（M7 の PR 4: 要確認・判定理由・通知）」→ ユーザーがマージ（PR #15、2026-10-04）

PR 5（`feat/m7-preview`）:

- [x] backend: レクチャーの詳細に、残す区間の余白（`keep_padding`）を足す（プレビューが、書き出しと同じ区間を残す）
- [x] 残す区間の計算（backend と同じ値で確かめる）と、カット後のタイムライン
- [x] プレビュー: 録画ファイルの切り替え、削除区間のスキップ（`requestVideoFrameCallback`）、文字起こしとの再生位置の同期
- [x] 実物の backend と proxy 動画、ヘッドレスの Chrome での確認（再生 → 削除区間を飛ばす → 文字の印 → クリック・時刻・バーでの移動 → 削除した部分も再生する。コンソールの失敗なし）
- [x] 画面の構成の確認（ユーザー。不在の間に推奨案で実装した。Design Doc 3-6 の「プレビュー」）
- [x] review-loop（Stage 0〜2 すべて PASS。docs-reviewer の BLOCK 1 回: Design Doc の PR 3 の節が古いままだった → 修正して PASS。同じ種類が 2 回目なので FRIC-005 に記録）→ PR #16（PR 4 の上に積む。向き先は `feat/m7-transcript-review`）
- [x] 手動確認（ユーザー）: `frontend/README.md` の「手で確かめる（M7 の PR 5: プレビュー）」→ ユーザーがマージ（PR #16、2026-10-04）

PR 6（`feat/m7-waveform`。`wavesurfer.js` 8 を追加）:

- [x] 画面の構成の提案と承認（ユーザー、2026-10-04。推奨案のまま。Design Doc 3-6 の「編集画面の波形」）
- [x] 事前の確認: `wavesurfer.js` 8.0.1 の API と、CSP の下での動き（一時フォルダに展開して、ヘッドレスの Chrome で 5 通りの CSP を確かめた）。`npm audit` は既知の脆弱性なし
- [x] 波形: wavesurfer.js + ピーク値 + regions による削除区間の表示（1 本につなげる、種類ごとの色、戻し済みは破線の枠、目盛り、拡大と縮小）
- [x] 波形からの操作: クリックで再生位置を移す、区間を選んで「戻す」/「削除に戻す」、ダブルクリックで切り替え（無音の候補を、ここで戻せる）
- [x] プレビュー・文字起こしとの同期（再生位置の線、再生中のページ送り、波形のクリックで文字起こしをスクロール）
- [x] CSP: `style-src 'unsafe-inline'` を外し、wavesurfer.js が差し込む `<style>` 1 つだけをハッシュで許可した。違反がコンソールに出ないことを確認
- [x] 実物の backend と、ヘッドレスの Chrome での確認（描画・クリック・区間の選択と採否・保存・拡大と縮小・再生との連動・配色・読めないときと再試行: 45 項目。
      録画ファイルを 2 本にした写しで、つなげた波形: 10 項目。コンソールの失敗と CSP の違反なし）
- [x] review-loop（Stage 0〜2 すべて PASS。BLOCK なし。提案を受けて、録画ファイルがないレクチャーの扱い・長い関数の分割・重複した定数の集約を反映）→ PR [#17](https://github.com/kanpyou-maki/vid-cut/pull/17)
- [x] 手動確認（ユーザー）: `frontend/README.md` の「手で確かめる（M7 の PR 6: 波形）」→ ユーザーがマージ（PR #17、2026-10-04）

PR 7（`feat/m7-export`）:

- [ ] 書き出しボタンと進捗、保存先の表示（backend: レクチャーの詳細に保存先を足す、Finder で開く API）

### M8: E2E と受け入れ（`test/m8-e2e`）

- [ ] Playwright: 投入 → 解析 → 編集 → 書き出し（ML と判定は偽の実装に差し替え）
- [ ] 実際の撮影素材 3 本で受け入れチェック（PRD 3-2）: 誤削除は 1 本あたり 2 件以下、作業時間は手作業の半分以下、書き出しの音ズレ 0 件
- [ ] フィラーを含む素材が手に入れば、フィラー検出を検証（Design Doc D-5）
- [ ] 間の調整（M5 の手動確認で出た要望）: 文の終わりのあとの間を長くする。編集画面のプレビュー（M7）で聞きながら、実際の撮影素材で値を決める。
      いまは無音の削除で、残す区間の前に 150ms・後ろに 250ms を残す（つなぎ目の間は最大 400ms）。文の終わりかどうかは文字起こしの句点で分かるので、データの作り直しは要らない

## 完了条件

- [ ] すべてのテストが通過し、カバレッジが 80% 以上
- [ ] 受け入れチェック（PRD 3-2）に合格
- [ ] 関連ドキュメントが更新されている
- [ ] `QUALITY_SCORE.md` が更新されている

## 進捗メモ

- 2026-10-03: M0 完了（`chore/m0-scaffold`）。backend: Python 3.12・pytest・ruff・mypy（strict）。frontend: React 19・Vite 8・TypeScript 6・vitest 5・Biome 2。テンプレート既定の oxlint は Biome に置き換えた
- 2026-10-03: M1 完了（`feat/m1-domain`）。domain に intervals / models / cuts / timeline / overrides。テスト 80 件、カバレッジ 100%。review-loop の指摘で、接する無音の統合、整数以外・NaN・負の許容幅の拒否を追加

- 2026-10-03: M4 完了（`feat/m4-judge`）。pipeline に judge（指示文・検証・窓分割）、adapters に claude_cli と sqlite/judgements、services に judge / judge_eval。
  `claude -p` は `--tools ""` と `--safe-mode` を付け、ワークスペースの `judge/` から呼ぶ。判定 1 回は検証素材（69 チャンク）で約 15 秒

- スパイクのスクリプト（xmeml の最小実装、ASR の計測）は使い捨て。知見は ADR-002・ADR-003 に記録済み
- ML の初回実行ではモデルのダウンロード（合計約 3GB、5 分程度）が発生する

## 完了後の手順

1. このファイルのステータスを `completed` に変更
2. `docs/exec-plans/completed/` へ移動
3. `docs/PLANS.md` のインデックスを更新
