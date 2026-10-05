# vid-cut

講座用に録画した動画（画面録画 + 日本語ナレーション）から、無音・フィラー・言い直しを自動で見つけてカットし、
Premiere Pro で続きを編集できる形（Premiere XML）で書き出す、ローカルのアプリ。

- 録画を読み込むと、無音・フィラー・言い直しが**削除済みの状態**で編集画面が開く
- 人は文字起こしを読み、怪しい箇所だけを確認して直す（削除済みの部分を押せば戻り、文字を選んで Delete で削れる）
- 言い直しの判定には `claude -p` を使う。それ以外（文字起こし・無音検出）は、すべて手元の Mac で動く

要件は [PRD](./docs/prd.md)、設計は [Design Doc](./docs/design.md)。

## 動作環境

- Apple Silicon の Mac（文字起こしに mlx-whisper を使う）
- [ffmpeg](https://ffmpeg.org/)、[uv](https://docs.astral.sh/uv/)、Node.js
- ログイン済みの `claude` CLI（言い直しの判定に使う。ログインしていないと、判定だけが失敗する。無音とフィラーのカットは使える）

## セットアップ

```bash
uv sync --directory backend --extra ml   # backend の依存と、ML のモデルを動かすライブラリ
npm --prefix frontend install            # frontend の依存
npm --prefix frontend run build          # 画面をビルドする
```

最初の解析では、ML のモデル（合計約 3GB）のダウンロードが走る。

## 使い方

```bash
uv run --directory backend vidcut serve
```

ブラウザで <http://127.0.0.1:8765/> を開く。

1. **投入**: 素材一覧の「投入…」で、録画ファイルを選んで投入する（複数を選べる）。解析（無音検出・文字起こし・フィラー検出）と、言い直しの判定が順に走る
2. **確認と修正**: 「編集待ち」になったレクチャーを開く。左にプレビュー、右に文字起こし、下に波形が出る
   - 削除済みの部分（色つき）を押すと戻る。もう一度押すと削除に戻る
   - 文字を選んで Delete で、手動で削る。⌘Z で取り消し、⇧⌘Z でやり直し
   - Space で再生と一時停止。N で次の要確認の箇所へ移る
   - カットの前後の間は、プレビューの下の「間の設定」で変えられる
3. **書き出し**: 「Premiere XML を書き出す」または「MP4 を書き出す」を押す。`~/VidCut/exports/<レクチャー名>/` にできる

編集の内容は自動で保存される。別のファイルに撮り直した録画は、素材一覧で 1 つのレクチャーにまとめられる。

### 更新したあと

`git pull` のあとは、画面をビルドし直してから、サーバーを起動し直す（ビルドし直さないと、前の画面が配信され続ける）。

```bash
npm --prefix frontend run build
uv run --directory backend vidcut serve
```

### データの置き場所

ワークスペースは `~/VidCut/`（環境変数 `VIDCUT_WORKSPACE` で変えられる）。データベース、解析の結果、中間素材、書き出したファイルが入る。
元の録画ファイルは、書き換えない。

## 知っておくとよい制限

- **フィラー**: フィラーと判定されても、声が少し残ることがある。画面では削れないので、Premiere で削る。
  続けて言ったフィラー（「あー、えーと」）は、自動では消えない（文字を選んで削る）
- **言い直し**: 判定は、無音で区切った発話のまとまりごと。まとまりの一部だけの言い直しは、自動では消えない
- **長いレクチャー**: 約 2 時間のレクチャーでは、波形を「全体」に切り替えるときに、約 3 秒固まる

詳しくは [Design Doc](./docs/design.md) の 3-2・3-6 と、[受け入れチェックの記録](./docs/references/acceptance-m8.md)。

## 開発

| 場所                                     | 中身                                                    |
| ---------------------------------------- | ------------------------------------------------------- |
| [backend/](./backend/README.md)          | 解析パイプラインとローカル API（Python 3.12 / FastAPI） |
| [frontend/](./frontend/README.md)        | 編集の画面（TypeScript / React / Vite）                 |
| [ARCHITECTURE.md](./ARCHITECTURE.md)     | ディレクトリの構成と、依存の決まり                      |
| [docs/adr/](./docs/adr/)                 | 技術的な決定の記録                                      |
| [PROJECT_STATUS.md](./PROJECT_STATUS.md) | いまの状態と、残っている任意の項目                      |
| [CLAUDE.md](./CLAUDE.md)                 | Claude Code での進め方（Discussion → Document → TDD）   |

テストなどのコマンドは `.claude/harness.json` の `commands` にまとめてある。

```bash
uv run --directory backend pytest   # backend のテスト
npm --prefix frontend test          # frontend のテスト
npm --prefix frontend run e2e       # E2E（Playwright。Google Chrome が要る）
```
