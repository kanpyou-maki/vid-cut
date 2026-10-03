# ARCHITECTURE.md

リポジトリのドメイン・パッケージ階層を示すトップレベルマップ。
エージェントはこのファイルを参照してリポジトリ構造を把握すること。

## ディレクトリ責務

### アプリケーション（M0 で `backend/`・`frontend/` の土台を作成済み。サブパッケージはマイルストーンごとに追加する）

技術選定は [ADR-001](./docs/adr/ADR-001-language-and-stack.md)、詳細は [Design Doc](./docs/design.md)。

| パス                              | 責務                                                                                                                                                                                                                                                                                                        | 主な変更者  |
| --------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------- |
| `backend/`                        | Python（uv プロジェクト）。解析パイプラインとローカル API                                                                                                                                                                                                                                                   | `tdd-guide` |
| `backend/src/vidcut/domain/`      | データモデル（発話・単語/文字単位タイミング・確信度・カット区間・編集決定）とレクチャー名の正規化（`titles.py`）。外部依存なし                                                                                                                                                                              | `tdd-guide` |
| `backend/src/vidcut/pipeline/`    | 各段の処理（音声抽出・VAD・文字起こし・位置合わせ・言い直し判定・書き出し）。`ports.py` に外部ツールと永続化の抽象（複数の保存をまとめて確定する `Atomic` を含む）。`prompts/` に判定の指示文。書き出しは `export.py`（残す区間の計画）と `xmeml.py`（Premiere XML）。`error_codes.py` は失敗を種別に分ける | `tdd-guide` |
| `backend/src/vidcut/adapters/`    | 外部ツールの境界（`media/`: ffmpeg、`sqlite/`: リポジトリとジョブ表、`ml/`: mlx-whisper / WhisperX / Silero、`workspace.py`: 生成物・書き出し先・fingerprint、`claude_cli.py`: `claude -p`）                                                                                                                | `tdd-guide` |
| `backend/src/vidcut/api/`         | FastAPI のルーティング（HTTP の関心事のみ）。`security.py`: ローカル API の防御、`inputs.py`: 入力スキーマ（厳格な型と上限）、`outputs.py`: 出力スキーマ（許可リスト）、`errors.py` / `messages.py`: 例外と失敗の種別を定型文の応答に直す、`routes/`: エンドポイント                                                                 | `tdd-guide` |
| `backend/src/vidcut/services/`    | ユースケース（取り込み・解析・言い直しの判定とその精度評価・書き出しとその依頼・レクチャーをまとめる / 並べ替える / 解除する / 解析し直す・編集の保存・一覧と詳細の組み立て・投入するファイルを選ぶ簡易ブラウザ）                                                                                           | `tdd-guide` |
| `backend/src/vidcut/jobs/`        | worker のループ。ジョブ表には `JobQueue` の port を通して触れる（[ADR-004](./docs/adr/ADR-004-local-app-runtime.md)）                                                                                                                                                                                       | `tdd-guide` |
| `backend/src/vidcut/bootstrap.py` | 依存の組み立て。ports に具象 adapters を注入する唯一の場所。`build_app`（worker と CLI。接続を 1 本持つ）と `build_api`（API。リクエストごとに接続を開く）                                                                                                                                                  | `tdd-guide` |
| `backend/src/vidcut/cli.py`       | コマンドライン（`serve` / `analyze` / `worker` / `eval`）                                                                                                                                                                                                                                                   | `tdd-guide` |
| `backend/tests/`                  | pytest（unit / integration）。重い ML とメディア処理はアダプタ境界でモックする                                                                                                                                                                                                                              | `tdd-guide` |
| `frontend/`                       | TypeScript + React + Vite。プレビュー・文字起こしエディタ・波形タイムライン                                                                                                                                                                                                                                 | `tdd-guide` |
| `frontend/src/test/`              | vitest の共通設定（jest-dom の読み込み、テストごとの後片付け）                                                                                                                                                                                                                                              | `tdd-guide` |
| `docs/references/prototype/`      | work-repo 時代のプロトタイプと正解データ（参照専用。改変しない）                                                                                                                                                                                                                                            | 人間        |

### リポジトリ基盤

| パス                    | 責務                                           | 主な変更者       |
| ----------------------- | ---------------------------------------------- | ---------------- |
| `CLAUDE.md`             | エージェントへのナビゲーション地図（≤100行）   | 人間 / Claude    |
| `ARCHITECTURE.md`       | このファイル。構造マップ                       | 人間 / Claude    |
| `PROJECT_STATUS.md`     | 現在の進捗状態                                 | Claude / 人間    |
| `.claude/agents/`       | サブエージェント定義 (`.md`、frontmatter 必須) | improve-harness  |
| `.claude/hooks/`        | Claude Code フック実装 (`.js`)                 | master から配布  |
| `.claude/rules/`        | コーディングルール (`{lang}/{category}.md`)    | master から配布  |
| `.claude/skills/`       | 再利用スキル (`{name}/SKILL.md`)               | master から配布  |
| `.claude/harness.json`  | ハーネスコマンド定義（test 等）                | bootstrap / 人間 |
| `.claude/settings.json` | Claude Code フック・パーミッション設定         | 人間             |
| `.claude/master-path`   | claude-config-master の場所（同期用）          | install.sh       |
| `docs/`                 | 知識ベース全体                                 | Claude / 人間    |
| `docs/adr/`             | アーキテクチャ決定レコード                     | `doc-updater`    |
| `docs/exec-plans/`      | 実行プラン（active/ / completed/）             | `planner`        |
| `docs/design-docs/`     | コンポーネント別詳細設計・中核的信念           | `doc-updater`    |
| `docs/friction-log.md`  | 摩擦ログ（ハーネス改善の入力）                 | 全エージェント   |

## 依存方向ルール

### アプリケーション（予定）

```
backend:  api / cli / jobs → services → pipeline → domain
          adapters → pipeline.ports / domain（ports の実装。pipeline・services は adapters を import しない）
          jobs は pipeline の ports と error_codes を直接使ってよい（ジョブ表と失敗の分類。services は handler として注入される）
          bootstrap.py だけが adapters を import して注入する
          domain は他のどのパッケージにも依存しない（字幕・テロップ用の文字単位タイミングを最初から保持する）
frontend → backend の HTTP API のみ（backend の内部構造に依存しない。型は API スキーマから生成）
```

### ハーネス

```
.claude/agents/   →  tools のみ利用。agents/ 間の相互依存禁止
.claude/hooks/    →  Node.js 標準ライブラリのみ（外部 npm 依存禁止）
.claude/rules/    →  独立。他ファイルへの依存は Markdown リンクのみ
.claude/skills/   →  独立。他ファイルへの依存は Markdown リンクのみ
docs/             →  自由にリンク可。docs/ 外への参照は相対パスで
.claude/settings.json  →  .claude/hooks/*.js のみ参照（ARCH-004 で整合性検証）
```

## アーキテクチャ規則（`.claude/hooks/arch-lint.js` が機械的に強制）

| 規則 ID  | 検査内容                                                                                |
| -------- | --------------------------------------------------------------------------------------- |
| ARCH-001 | エージェント定義 (`.md` with `name:` frontmatter) は `.claude/agents/` 以外に配置しない |
| ARCH-002 | `.claude/` 配下のフック実装 (`.js`) は `.claude/hooks/` 以外に配置しない                |
| ARCH-003 | `.claude/rules/` 配下のファイルは `{lang}/{category}.md` の命名規則に従う               |
| ARCH-004 | `.claude/settings.json` が参照するフックファイルが実在する                              |
| ARCH-005 | `CLAUDE.md` は常に 100行以内                                                            |
| ARCH-006 | `.md` ファイル内の相対リンクが実在するファイルを指している（コードブロック内は除外）    |

## 知識グラフ

ドキュメントは CLAUDE.md を根とする有向グラフを構成する（ノード = `.md`、エッジ = 相対リンク）。

- エッジの有効性は ARCH-006 が強制する（リンク切れ = 違反）
- ノードの到達可能性は `structure-test.js` が検証する（孤立ドキュメント = 警告）
- エージェントのコンテキストから辿れないドキュメントは存在しないのと同じ。新しいドキュメントは必ずグラフに接続すること
