# vid-cut frontend

編集 UI（TypeScript + React + Vite）。構成は [ARCHITECTURE.md](../ARCHITECTURE.md) と [Design Doc](../docs/design.md) を参照。

```bash
npm install
npm run dev        # 開発サーバー（/api は backend の 127.0.0.1:8765 へ転送）
npm test           # テスト（vitest）
npm run coverage   # カバレッジ（80% 未満で失敗）
npm run typecheck  # 型チェック
npm run lint       # Biome（lint + フォーマット確認）
```
