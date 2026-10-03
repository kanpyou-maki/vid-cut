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
uv run vidcut worker                                # 積まれたジョブを順に処理し続ける
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
