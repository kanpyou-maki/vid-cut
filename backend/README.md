# vid-cut backend

解析パイプラインとローカル API（Python 3.12 / uv）。構成は [ARCHITECTURE.md](../ARCHITECTURE.md) と [Design Doc](../docs/design.md) を参照。

```bash
uv sync                 # 開発用の依存を導入
uv sync --extra ml      # 実物の ML モデル（mlx-whisper / WhisperX / Silero VAD）も導入
uv run pytest           # テスト（ML を使うテストは除外）
uv run pytest -m ml     # ML を使うテストだけ実行
```
