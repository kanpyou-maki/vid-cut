# 摩擦ログ (Friction Log)

エージェントが作業中に遭遇した「繰り返す摩擦」を記録するファイル。
ハーネス自己改善ループの**入力**であり、`improve-harness` スキルがこのログを消費して
`.claude/` 配下の設定（agents / hooks / rules / skills）の改善に変換する。

## 記録ルール

- **記録するもの:** 同種の問題が 2回以上起きたとき、review-loop で同一ステージの BLOCK が 3回続いたとき、ツール・ドキュメント・ガードレールの不足で手戻りが生じたとき
- **記録しないもの:** 一度きりの実装ミス（それは通常の修正で終わり）
- 各エントリは「何が起きたか」ではなく「**なぜ繰り返すのか**」まで書くこと
- `improve-harness` で解消したエントリは Status を `resolved` にし、対応した変更（PR・コミット）を記録すること

## エントリ形式

```markdown
### FRIC-NNN: <短いタイトル>

- **日付:** YYYY-MM-DD
- **状況:** 何をしていて、何に繰り返しつまずいたか
- **根本原因の仮説:** ツール不足 / ガードレール不足 / ドキュメント不足 / エージェント指示の曖昧さ
- **改善候補:** どのファイル（.claude/agents|hooks|rules|skills、docs/）をどう変えるか
- **Status:** open | resolved (<PR/コミット>)
```

---

## エントリ

### FRIC-001: settings.json の `Write(~/.ssh/*)` 等の deny ルールが効いていない

- **日付:** 2026-10-03
- **状況:** `claude -p` の動作確認時に、Claude Code が「`Write(path)` はファイル権限の検査に使われない。`Edit(path)` を使うこと」と警告した。
  `~/.ssh`・`~/.aws`・`~/.gnupg` への書き込み禁止が実際には効いていない
- **根本原因の仮説:** ガードレール不足。master（claude-config-master）の settings.json テンプレートが古い記法のまま配布されている。
  arch-lint にも deny ルールの記法を検査する規則がない
- **改善候補:** `.claude/settings.json` の 3 行を `Edit(~/.ssh/*)` 等に変更（Claude の自己改変にあたるため人が行う）→ sync-upstream で master に還元。
  `.claude/rules/common/security.md` の記述も合わせて確認する
- **Status:** resolved（vid-cut: ユーザーが settings.json を修正 / master: [claude-config-master#2](https://github.com/kanpyou-maki/claude-config-master/pull/2)）

### FRIC-002: プロジェクト内で `claude -p` を呼ぶと、ハーネスの設定と CLAUDE.md が読み込まれる

- **日付:** 2026-10-03
- **状況:** リポジトリ直下で `claude -p` を実行すると、プロジェクトの settings.json（と CLAUDE.md）が読み込まれた。
  vid-cut は言い直しの判定に `claude -p` を使うため、判定の入力に開発用の指示が混ざり、トークンも余計に消費する
- **根本原因の仮説:** ドキュメント不足（`claude -p` をアプリの部品として使う場合の注意点がない）
- **改善候補:** Design Doc 3-3 に「作業ディレクトリをワークスペースの中立なディレクトリにし、ツールを使わせない」と記載した（対応済み）。
  実装時に adapter のテストで、作業ディレクトリの指定を検証する
- **Status:** open

### FRIC-003: フックが backend/ ・ frontend/ のサブディレクトリ構成に対応していない

- **日付:** 2026-10-03
- **状況:** M0 で `frontend/biome.json` を置いたが、quality-gate フックはリポジトリ直下の `biome.json` しか探さず、frontend の `.ts` / `.tsx` / `.css` を `npx prettier` で整形する。
  CSS の `font-family` の改行規則で Prettier と Biome が衝突し、編集のたびに `npm run lint` が落ちうる。
  また post-edit-typecheck は最寄りの `tsconfig.json`（Vite のソリューション形式で `files: []`）で `tsc --noEmit` を実行するため、何も検査しない
- **根本原因の仮説:** ツール不足。フックが単一パッケージ構成（ルート直下に設定ファイル）を前提にしている
- **改善候補:** quality-gate はファイルから上位へ辿って最寄りの `biome.json` を探し、そのディレクトリのローカル Biome で整形する。
  post-edit-typecheck は `references` を持つ tsconfig なら `tsc -b` を使う。いずれも汎用的なので sync-upstream で master に還元する。
  当面の回避策: Biome の整形設定を Prettier の既定に合わせ（2 スペース・80 桁・ダブルクォート・セミコロン）、CSS は両者で結果が同じになる書き方にする
- **Status:** resolved（フックを修正しテスト 14 件を追加。master: [claude-config-master#3](https://github.com/kanpyou-maki/claude-config-master/pull/3)。vid-cut には同じフックを取り込み済み）


### FRIC-004: Python のルール文書が black / isort を指定しているが、プロジェクトは ruff format を使う

- **日付:** 2026-10-03
- **状況:** M2・M3 の review-loop で、style-reviewer が 2 回続けて「`.claude/rules/python/coding-style.md` は black と isort を指定しているが、実態は ruff format」と指摘した。
  毎回、依頼文で「ruff format を使う」と断りを入れる必要があり、断りを忘れると誤った BLOCK になりうる
- **根本原因の仮説:** ドキュメント不足。master から配布されるルール文書が特定の整形ツールを名指ししており、プロジェクトの選択（`backend/pyproject.toml` の ruff）と `harness.json` の `lint` コマンドを参照していない
- **改善候補:** `.claude/rules/python/coding-style.md` の「Formatting Tools」を「整形と lint は `.claude/harness.json` の `lint` コマンド（このプロジェクトは ruff format / ruff check）に従う」に書き換える。
  汎用的な改善なので sync-upstream で master に還元し、style-reviewer の確認項目も同じ表現にそろえる
- **対応:** ルール文書はツールを名指しせず `commands.lint` を正とした。style-reviewer に「整形・lint は `commands.lint` の結果で判定し、ツールの種類は問わない」を追加。
  python-patterns スキルの早見表も同じ方針に直した。vid-cut の `commands.lint` には `ruff format --check` を加え、整形の崩れを機械的に検出する
- **Status:** resolved（vid-cut: [#6](https://github.com/kanpyou-maki/vid-cut/pull/6)。master: [claude-config-master#4](https://github.com/kanpyou-maki/claude-config-master/pull/4)）
