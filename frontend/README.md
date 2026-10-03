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

開発中は、backend を `uv run --directory ../backend vidcut serve --dev` で起動してから `npm run dev` を使い、`http://localhost:5173/` を開く。

- API はトークン（`X-VidCut-Token`）を求める。開発中は Vite のプラグイン（`vite-plugins/devToken.ts`）が、HTML を返すたびに backend の画面の HTML からトークンを読んで埋め込む（[ADR-006](../docs/adr/ADR-006-frontend-foundation.md)）
- 画面に「トークンを読み取れませんでした」と出たら、backend が起動していない。起動してから読み込み直す
- backend を起動し直すとトークンが変わる。「トークンが正しくありません」と出たら読み込み直す
- 5173 番が使われていると、開発サーバーは起動しない（backend は 5173 番のオリジンだけを受け付ける）

## 構成

| フォルダ        | 中身                                                                                |
| --------------- | ----------------------------------------------------------------------------------- |
| `src/app/`      | 画面の枠（見出し、パスに応じた画面の出し分け）                                      |
| `src/library/`  | 素材一覧（`/`）。一覧、投入ダイアログ、まとめる・並べ替え・解除、失敗の再実行       |
| `src/editor/`   | 編集画面（`/lectures/{id}`）                                                        |
| `src/shared/`   | 画面をまたいで使う部品（画面の切り替え、ポーリング、ダイアログ）                    |
| `src/api/`      | API クライアント（画面は `Api` のインターフェースだけを使う）、トークン、失敗の種類 |
| `vite-plugins/` | 開発サーバー用のプラグイン                                                          |

依存の向きは `app → library・editor → shared → api`。

画面の実装で守ること（[Design Doc](../docs/design.md) 3-5-1・3-6）:

- トークンは meta 要素から読み、API クライアントの中だけで持つ。`localStorage`・URL・ログに残さない
- `dangerouslySetInnerHTML` を使わない（判定の理由やファイル名は、React の通常の描画で表示する）
- 外部の CDN・フォント・画像を使わない（CSP は `default-src 'self'`）
- 画面に出す失敗の文は `errorMessage`（`src/api/errors.ts`）を通す（例外の文をそのまま出さない）
- ダイアログは `Modal`（`src/shared/Modal.tsx`。`dialog` 要素の `showModal`）を使う。jsdom は `showModal` を持たないので、テストでは `src/test/setup.ts` の代わりの実装が働く
- 一覧を変える操作のあとは、`usePolling` の `refresh` ですぐに読み直す

`src/api/generated/` は生成物（`openapi.json` と `schema.d.ts`）。手で編集せず、backend の API を変えたら `npm run gen:api` で作り直してコミットする。
`openapi-typescript` 7 は peer 依存が TypeScript 5 のため、`package.json` の `overrides` でこのプロジェクトの TypeScript 6 を使わせている（TypeScript 6 で生成と型チェックが通ることを確認済み）。

## 手で確かめる（M7 の PR 1: 土台）

実データを書き換えないよう、ワークスペースの写し（`cp -R ~/VidCut ~/VidCut-check`）で行う。コマンドはリポジトリのルートで実行する。

**1. 開発中（Vite の開発サーバー）**

```bash
VIDCUT_WORKSPACE=~/VidCut-check uv run --directory backend vidcut serve --dev   # ターミナル 1
npm --prefix frontend run dev                                                   # ターミナル 2
```

http://localhost:5173/ を開いて確かめる。

- 素材一覧に `s05-12sample`（編集待ち）が出る
- 名前をクリックすると編集画面（準備中）に移り、「素材一覧へ戻る」とブラウザの「戻る」で一覧に戻る。編集画面で読み込み直しても、編集画面のまま
- ターミナル 1 を Ctrl+C で止めると、1〜2 秒で「サーバーに接続できません」と出る（一覧は残る）
- ターミナル 1 を起動し直すと「トークンが正しくありません。ページを読み込み直してください」と出て、読み込み直すと直る

**2. 本番（ビルドした画面を backend が配信する）**

```bash
npm --prefix frontend run build
VIDCUT_WORKSPACE=~/VidCut-check uv run --directory backend vidcut serve
```

http://127.0.0.1:8765/ を開いて、1 と同じ一覧が出ることを確かめる。開発者ツールで次も確かめる。

- コンソールに CSP の違反（`Content Security Policy` を含むエラー）が出ていない
- Application → Local Storage / Session Storage が空（トークンを保存していない）

確かめたあとは、サーバーを Ctrl+C で止め、`pgrep -fl "vidcut.cli"` で残りがないことを確かめる。

## 手で確かめる（M7 の PR 2: 素材一覧）

実データを書き換えないよう、ワークスペースの写しと、検証素材から切り出した短い動画で行う。コマンドはリポジトリのルートで実行する。

**準備**

```bash
cp -R ~/VidCut ~/VidCut-check
mkdir -p ~/vidcut-check-clips/sub
for i in 1 2 3; do
  ffmpeg -v error -ss $(( (i - 1) * 20 )) -t 20 -i ~/Desktop/s05-12sample.mov -c copy ~/vidcut-check-clips/part$i.mov
done
npm --prefix frontend run build
VIDCUT_WORKSPACE=~/VidCut-check uv run --directory backend vidcut serve
```

http://127.0.0.1:8765/ を開いて、順に確かめる。

**1. 一覧と投入**

- 一覧に `s05-12sample`（編集待ち）が出て、右に本数と合計時間（`1 本・…`）が出る
- 「投入…」でダイアログが開く。ホームから始まり、フォルダ名（末尾に `/`）を押すと中へ移動する。「上へ」「ホーム」で戻れる（ホームでは「上へ」を押せない）
- `vidcut-check-clips` に入ると、`sub/` と `part1.mov`〜`part3.mov` が出る。Esc か「キャンセル」で閉じ、もう一度「投入…」を押すと、同じフォルダから始まる
- 「すべて選ぶ」で 3 件にチェックが入り、ボタンが「投入（3 件）」になる。`sub/` に入って戻ると、チェックは消えている
- 3 件を選んで「投入（3 件）」を押したら、**すぐに**別のターミナルで `rm ~/vidcut-check-clips/part3.mov` を実行する（あとで失敗の表示を確かめる）
- ダイアログが閉じ、一覧の上に「投入の結果: 追加 3 件・登録済み 0 件・失敗 0 件」と出る。「閉じる」で消える
- `part1`・`part2` の状態が、待機中 → 解析中 n% → 判定中 → 編集待ち と変わる（読み込み直さなくてよい）
- もう一度 `part1.mov` を投入すると「追加 0 件・登録済み 1 件・失敗 0 件」と出る

**2. 失敗と再実行**

- `part3` が「失敗」になり、行の下に「解析（part3.mov）: 録画ファイルが見つかりません。…」と「再実行」が出る
- 動画を作り直してから（`ffmpeg -v error -ss 40 -t 20 -i ~/Desktop/s05-12sample.mov -c copy ~/vidcut-check-clips/part3.mov`）「再実行」を押すと、解析が進んで「編集待ち」になる

**3. まとめる・並べ替え・解除**

- チェックが 1 件以下のときは「まとめる」を押せない。`part2`、`part1` の順にチェックすると「まとめる（2 件）」になる
- 押すと、題名の初期値が `part1`（一覧で上にあるほう）のダイアログが開き、まとめる順番が `part1.mov`、`part2.mov` と出る。題名を空にすると「まとめる」を押せない
- 題名を入れて「まとめる」を押すと、2 つのレクチャーが 1 つになり（`2 本・…`）、録画ファイルが番号付きで出る。判定がやり直される（判定中 → 編集待ち）。チェックは外れている
- 録画ファイルの ↑ ↓ を押すと、順番が入れ替わる（先頭の ↑ と末尾の ↓ は押せない）。判定がやり直される
- 「解除」を押すと確認が出る。「キャンセル」と Esc では何も起きない。「解除する」で、録画ファイルごとのレクチャー（題名はファイル名）に戻る

**4. 失敗の表示（サーバーを止める）**

- サーバーを Ctrl+C で止めると、1〜2 秒で「サーバーに接続できません」と出る（一覧は残る）。その状態で ↑ ↓ や「再実行」を押しても、同じ文が出るだけで画面は壊れない

開発者ツールで次も確かめる。

- コンソールに CSP の違反（`Content Security Policy` を含むエラー）が出ていない
- Application → Local Storage / Session Storage が空

確かめたあとは、サーバーを Ctrl+C で止め、`pgrep -fl "vidcut.cli"` で残りがないことを確かめて、`rm -rf ~/VidCut-check ~/vidcut-check-clips` で片付ける。
