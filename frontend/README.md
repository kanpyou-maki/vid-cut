# vid-cut frontend

編集 UI（TypeScript + React + Vite）。構成は [ARCHITECTURE.md](../ARCHITECTURE.md) と [Design Doc](../docs/design.md) を参照。

```bash
npm install
npm run dev        # 開発サーバー（/api は backend の 127.0.0.1:8765 へ転送）
npm test           # テスト（vitest）
npm run coverage   # カバレッジ（80% 未満で失敗）
npm run typecheck  # 型チェック
npm run lint       # Biome（lint + フォーマット確認）と、API の型が最新かの確認
npm run build      # 本番用のビルド（dist/。`vidcut serve` が配信する）
npm run gen:api    # backend の OpenAPI から API の型を作り直す（src/api/generated/）
```

開発中は、backend を `uv run --directory ../backend vidcut serve --dev` で起動してから `npm run dev` を使う。

`src/api/generated/` は生成物（`openapi.json` と `schema.d.ts`）。手で編集せず、backend の API を変えたら `npm run gen:api` で作り直してコミットする。
`openapi-typescript` 7 は peer 依存が TypeScript 5 のため、`package.json` の `overrides` でこのプロジェクトの TypeScript 6 を使わせている（TypeScript 6 で生成と型チェックが通ることを確認済み）。
