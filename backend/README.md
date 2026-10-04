# vid-cut backend

解析パイプラインとローカル API（Python 3.12 / uv）。構成は [ARCHITECTURE.md](../ARCHITECTURE.md) と [Design Doc](../docs/design.md) を参照。

```bash
uv sync                 # 開発用の依存を導入
uv sync --extra ml      # 実物の ML モデル（mlx-whisper / WhisperX / Silero VAD）も導入
uv run pytest           # テスト（ML を使うテストは除外）
uv run pytest -m ml     # ML を使うテストだけ実行
uv run ruff check . && uv run ruff format --check .   # lint と整形の確認（直すときは ruff format .）
```

## コマンドライン

```bash
uv run vidcut analyze ~/Movies/S05-12.mov --wait   # 取り込んで、この場で解析まで実行
uv run vidcut analyze ~/Movies/course/              # フォルダ直下の動画を取り込み、ジョブだけ積む
uv run vidcut worker                                # 積まれたジョブを順に処理し続ける（serve は自分で worker を起動する）
uv run vidcut reanalyze --wait                      # 登録済みの録画をすべて解析し直す（解析のしかたを変えたあと）
```

`reanalyze` は、フィラーの検出などを変えたあとに、登録済みの録画に当て直すためのもの。文字起こしなどの段は作り直さないので、すぐ終わる（4 本で 1 秒未満）。
言い直しの判定は、入力（文字起こし）が同じなら `claude` を呼ばずに前の結果のまま。手動の削除と、言い直しの候補の戻しも変わらない。
戻していた無音・フィラーは、区間が重なる新しい候補へ引き継ぐ（id は「何番目か」で決まるので、id では対応づけない。Design Doc 3-2）。`--wait` を付けなければ、ジョブを積むだけ（`vidcut serve` の worker が処理する）。

解析が終わると、言い直しの判定（`claude -p`）が続けて実行される。`claude` にログインしていないと判定だけが失敗する
（無音とフィラーの削除候補は使える）。ターミナルで `claude` を起動して `/login` を実行すること。

## 判定の精度評価

正解データ（削除するチャンクの id）と比べて、適合率・再現率を出す。`claude -p` を呼ぶ（1 回 15 秒ほど）。
目標（適合率 90% 以上・再現率 80% 以上）に届かなければ終了コード 1。

```bash
# プロトタイプのチャンク一覧（whisper.cpp の文字起こし）で測る
uv run vidcut eval judge --chunks ../docs/references/prototype/sample-chunks.json \
  --truth ../docs/references/prototype/sample-judge-ground-truth.json

# 解析済みのレクチャー（題名または id）で測る。正解の id はレクチャー内のチャンクの通し番号（0 始まり）
uv run vidcut eval judge --lecture s05-12sample \
  --truth ../docs/references/prototype/sample-judge-ground-truth.json --runs 3
```

ワークスペースは既定で `~/VidCut/`（環境変数 `VIDCUT_WORKSPACE` で変更）。
環境変数 `VIDCUT_REVEAL=off` を付けると、「Finder で開く」（`POST /api/lectures/{id}/exports/reveal`）が `open` を実行せず、見せるはずだった場所をログに出すだけになる
（自動の確認と E2E 用。`off` 以外の値は起動時に失敗する。[Design Doc](../docs/design.md) 3-5-1）。

## 画面と API のサーバー

```bash
npm --prefix ../frontend run build   # 画面をビルドする（初回と、画面を変えたとき）
uv run vidcut serve                  # http://127.0.0.1:8765/ を開く。worker も一緒に起動する
uv run vidcut serve --port 9000      # ポートを変える
uv run vidcut serve --no-worker      # worker を起動しない（別に `vidcut worker` を動かすとき）
uv run vidcut serve --dev            # 開発中: Vite の開発サーバー（npm run dev）からの要求も受け付ける
```

- 待ち受けは 127.0.0.1 だけ。起動のたびにトークンを作り、画面の HTML に埋め込む（[Design Doc](../docs/design.md) 3-5-1）。
  API を直接呼ぶときは、`X-VidCut-Token` ヘッダーにそのトークンを付ける
- 画面のビルドがなければ、ビルドの手順を書いたページ（503）を返す。このページにもトークンが入る（開発中は、Vite のプラグインがそこから読む。[ADR-006](../docs/adr/ADR-006-frontend-foundation.md)）
- Ctrl+C（または SIGTERM）で、サーバーと worker の両方が止まる
- エンドポイントの一覧と入力の上限は Design Doc の 3-5。API を変えたら、frontend の型を作り直す: `npm --prefix ../frontend run gen:api`

### 手で確かめる（M6）

実データを書き換えないよう、ワークスペースの写しで行う（まとめる・解除・再解析は DB を書き換え、再解析は `claude -p` の判定も走らせる）。

**1. 写しを作って起動する**（このターミナルは起動したままにする）

```bash
cp -R ~/VidCut ~/VidCut-check                          # 中間素材を含むので数百 MB
VIDCUT_WORKSPACE=~/VidCut-check uv run vidcut serve
```

ブラウザで http://127.0.0.1:8765/ を開くと、画面（いまは土台だけ）が出る。

**2. 別のターミナルで、トークンを読んで API を呼ぶ準備をする**

```bash
BASE=http://127.0.0.1:8765
TOKEN=$(curl -s $BASE/ | sed -n 's/.*name="vidcut-token" content="\([^"]*\)".*/\1/p')
api() { curl -s -H "X-VidCut-Token: $TOKEN" "$@"; }
show() { python3 -m json.tool | head -${1:-40}; }
field() { python3 -c "import json,sys; d=json.load(sys.stdin)['data']; print($1)"; }
```

**3. 一覧・詳細・ジョブ・フォルダ**

```bash
api $BASE/api/lectures | show                 # s05-12sample が status: ready
LECTURE=$(api $BASE/api/lectures | field "d[0]['id']")
RECORDING=$(api $BASE/api/lectures | field "d[0]['recordings'][0]['id']")
api $BASE/api/lectures/$LECTURE | field "d['status'], len(d['recordings'][0]['tokens']), len(d['judged_suggestions'])"
                                              # 状態、文字数、言い直しの削除候補の件数
api $BASE/api/jobs | show 30                  # ジョブの一覧（error_code はあっても、生のエラー文は出ない）
api $BASE/api/fs | show 20                    # ホームの一覧（隠しフォルダは出ない）
```

**4. 動画（Range）と波形**

```bash
curl -s -o /dev/null -w "%{http_code} %{size_download} バイト\n" -H "Range: bytes=0-999" \
  "$BASE/api/recordings/$RECORDING/proxy?token=$TOKEN"          # 206 1000 バイト
api $BASE/api/recordings/$RECORDING/peaks | field "d['per_second'], len(d['values'])"
```

**5. 編集の保存と書き出し**

```bash
VERSION=$(api $BASE/api/lectures/$LECTURE | field "d['edit_state']['version']")
api -X PUT -H "Content-Type: application/json" \
  -d "{\"version\": $VERSION, \"restored_suggestion_ids\": [], \"manual_cuts\": []}" \
  $BASE/api/lectures/$LECTURE/edits | show     # version が 1 つ進む。同じ内容をもう一度送ると 409
api -X POST -H "Content-Type: application/json" -d '{"format": "premiere_xml"}' \
  $BASE/api/lectures/$LECTURE/exports | show   # worker が処理し、~/VidCut-check/exports/s05-12sample/ にできる
api $BASE/api/lectures/$LECTURE/exports | show # 保存先、形式ごとのパス・最後に書き出した日時・最新のジョブ
api -X POST $BASE/api/lectures/$LECTURE/exports/reveal | show  # Finder の窓が開き、書き出した XML が選ばれる
```

`reveal` は、実際に Finder の窓を開く（開かせたくなければ、サーバーを `VIDCUT_REVEAL=off` を付けて起動する）。
まだ書き出していないレクチャーでは 422（「書き出したファイルがまだありません」）。

**6. 断られることの確認**

```bash
curl -s -o /dev/null -w "%{http_code}\n" $BASE/api/lectures                     # 401（トークンなし）
curl -s -o /dev/null -w "%{http_code}\n" -H "Host: evil.example" $BASE/          # 403（別の Host）
api -o /dev/null -w "%{http_code}\n" "$BASE/api/fs?path=/etc"                    # 422（ホームの外）
```

**7. 止めて、片付ける**

起動したターミナルで Ctrl+C を押す（worker も一緒に止まる。`pgrep -fl "vidcut.cli"` で何も出なければよい）。

```bash
rm -rf ~/VidCut-check
```

## E2E 用の起動スクリプト（`tests/e2e/`）

画面の E2E（`frontend/e2e/`。Playwright）が使う。ML と判定だけを偽の実装に差し替えて、serve と worker を起動する（[Design Doc](../docs/design.md) 6 章）。

```bash
uv run python -m tests.e2e.serve --root <フォルダ> --port 8799 --frontend-dist <ビルドの出力>
```

- 本体（`src`）には、差し替えのための環境変数も偽の実装もない。差し替えは、`build_app` の引数（`ml`・`model`）、`cli.main` の `build`、`serve` の `start_worker` で行う
- `--root` には、ワークスペース（`workspace/`）と素材（`home/`。ffmpeg の `lavfi` で作る 13 秒の録画 2 本）を、実行のたびに作り直す。
  消すのは、このスクリプトが作ったフォルダ（目印のファイル `vidcut-e2e-root` がある）だけで、ほかのフォルダを指定すると、消さずに失敗する
- ワークスペースは `<root>/workspace` に固定（`VIDCUT_WORKSPACE` は見ない）。`VIDCUT_REVEAL=off` を自分で付ける
- 台本（素材の発話の区間と、偽の文字起こし・偽の判定が返す内容）は `tests/e2e/script.json`。画面側の E2E も同じファイルを読む
- 通常のテスト（`uv run pytest`）は、台本・偽の実装・フォルダの守り・取り込みから書き出しまで（実物の ffmpeg）を確かめる。サーバーの起動は、画面の E2E が確かめる

## 書き出し

Premiere XML と MP4 は、ジョブ `export_premiere` / `export_mp4` がワークスペースの `exports/<レクチャー名>/` に書き出す
（`<レクチャー名>.xml` と `<レクチャー名>.mp4`。Premiere XML は `recordings/<id>/mezzanine.mp4` を参照する）。
書き出しは、編集画面の書き出しの行（[frontend/README.md](../frontend/README.md) の「手で確かめる（M7 の PR 7: 書き出し）」）か、
API（`POST /api/lectures/{id}/exports`。上の「手で確かめる」を参照）から依頼する。書き出しの CLI はない。
保存先と、形式ごとの最後に書き出した日時・最新のジョブは `GET /api/lectures/{id}/exports`（レクチャーの詳細の `exports` と同じ）で読める。
同じ名前のレクチャーは同じ場所に書き出す（上書きになる。そのときは `shared_with_other_lectures` が true）。

無音を削るときに残す余白（前・後ろ・文の終わりのあと。既定は 150・250・500ms）は、編集画面の「間の設定」か `PUT /api/settings` で変えられる
（`{"keep_padding": {"before_ms": 150, "after_ms": 250, "after_sentence_ms": 800}}`。0〜2000 の整数。`null` で既定値に戻す）。
保存した値はワークスペースの SQLite（`settings` 表）に 1 組だけ持ち、すべてのレクチャーに効く。書き出しのジョブは、実行するときにこの値を読む（worker を起動し直す必要はない）。
