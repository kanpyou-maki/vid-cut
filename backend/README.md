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
```

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
- Ctrl+C（または SIGTERM）で、サーバーと worker の両方が止まる
- エンドポイントの一覧と入力の上限は Design Doc の 3-5。API を変えたら、frontend の型を作り直す: `npm --prefix ../frontend run gen:api`

### 手で確かめる（M6）

実データを書き換えないよう、ワークスペースの写しで行う（まとめる・解除・再解析は DB を書き換え、再解析は `claude -p` の判定も走らせる）。

```bash
cp -R ~/VidCut ~/VidCut-check                              # 写しを作る（中間素材を含むので数百 MB）
VIDCUT_WORKSPACE=~/VidCut-check uv run vidcut serve        # 別のターミナルで起動したままにする

# 以下は別のターミナルで。トークンは画面の HTML から読む
TOKEN=$(curl -s http://127.0.0.1:8765/ | sed -n 's/.*name="vidcut-token" content="\([^"]*\)".*/\1/p')
api() { curl -s -H "X-VidCut-Token: $TOKEN" "$@"; }

api http://127.0.0.1:8765/api/lectures | python3 -m json.tool | head -40    # 一覧（s05-12sample が ready）
LECTURE=$(api http://127.0.0.1:8765/api/lectures | python3 -c 'import json,sys; print(json.load(sys.stdin)["data"][0]["id"])')
api http://127.0.0.1:8765/api/lectures/$LECTURE | python3 -c 'import json,sys; d=json.load(sys.stdin)["data"]; r=d["recordings"][0]; print(d["status"], len(r["tokens"]), "文字", len(r["suggestions"]), "+", len(d["judged_suggestions"]), "件の削除候補")'
api http://127.0.0.1:8765/api/jobs | python3 -m json.tool | head -30        # ジョブの一覧
api "http://127.0.0.1:8765/api/fs" | python3 -m json.tool | head -20        # ホームの一覧（隠しフォルダは出ない）

# 動画（Range）。ブラウザでは <video src=".../proxy?token=..."> で再生できる
RECORDING=$(api http://127.0.0.1:8765/api/lectures | python3 -c 'import json,sys; print(json.load(sys.stdin)["data"][0]["recordings"][0]["id"])')
curl -s -o /dev/null -w "%{http_code} %{size_download} バイト\n" -H "Range: bytes=0-999" "http://127.0.0.1:8765/api/recordings/$RECORDING/proxy?token=$TOKEN"   # 206 1000 バイト

# 書き出し（worker が処理する。終わると ~/VidCut-check/exports/s05-12sample/ にできる）
api -X POST -H "Content-Type: application/json" -d '{"format": "premiere_xml"}' http://127.0.0.1:8765/api/lectures/$LECTURE/exports | python3 -m json.tool

# 断られることの確認
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8765/api/lectures                              # 401（トークンなし）
curl -s -o /dev/null -w "%{http_code}\n" -H "Host: evil.example" http://127.0.0.1:8765/                   # 403（別の Host）
api -o /dev/null -w "%{http_code}\n" "http://127.0.0.1:8765/api/fs?path=/etc"                             # 422（ホームの外）

rm -rf ~/VidCut-check                                      # 確かめ終わったら写しを消す
```

## 書き出し

Premiere XML と MP4 は、ジョブ `export_premiere` / `export_mp4` がワークスペースの `exports/<レクチャー名>/` に書き出す
（`<レクチャー名>.xml` と `<レクチャー名>.mp4`。Premiere XML は `recordings/<id>/mezzanine.mp4` を参照する）。
書き出しは API（`POST /api/lectures/{id}/exports`。上の「手で確かめる」を参照）と、M7 の画面から依頼する。
