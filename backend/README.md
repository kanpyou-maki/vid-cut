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

ワークスペースは既定で `~/VidCut/`（環境変数 `VIDCUT_WORKSPACE` で変更）。
