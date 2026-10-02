# bootstrap スキル — 新規プロジェクトの自律的初期化

`install.sh` によるスキャフォールド展開後、Claude が自律的にギャップを検出・修正・カスタマイズするスキル。
人間が静的テンプレートをそのまま使うのではなく、**プロジェクト固有の文脈をリポジトリに書き込む**ことが目的。

参考: [docs/design-docs/core-beliefs.md](../../../docs/design-docs/core-beliefs.md) — 原則 6

---

## 前提条件

```bash
# install.sh が実行済みであること（未実行なら先に実行）
./install.sh [typescript|python|both] /path/to/target-project
```

以降の手順はすべて **target project のルートディレクトリ** で実行する。

---

## Step 1: 現状スキャン（ギャップ検出）

### 1-1. 構造整合性チェック

```bash
node .claude/hooks/structure-test.js
```

エラーがあれば Step 2 で対処する。エラーがなければ次へ。

### 1-2. 必須ファイルの存在確認

以下のファイルが存在するか確認する:

```bash
ls -la CLAUDE.md ARCHITECTURE.md PROJECT_STATUS.md docs/prd.md docs/design.md 2>&1
```

存在しないファイルは Step 2 で生成する。

### 1-3. プロジェクト固有情報の収集

以下の情報を確認・収集する（不明なものは人間に確認する）:

| 情報 | 取得元 | 例 |
|------|-------|-----|
| プロジェクト名・目的 | 人間への確認 or README.md | 「社内勤怠管理 API」 |
| 技術スタック | package.json, pyproject.toml, 既存コード | TypeScript + Node.js + PostgreSQL |
| 主要ディレクトリ | `ls -la` | src/, tests/, infra/ |
| テストコマンド | package.json scripts / pyproject.toml | `npm test`, `pytest` |
| 既存の CI 設定 | .github/workflows/, .gitlab-ci.yml | GitHub Actions |

---

## Step 2: ギャップの自律修正

検出したギャップを **人間の介入なし** で以下の順序で修正する:

### 2-1. CLAUDE.md のカスタマイズ

テンプレートの CLAUDE.md を、このプロジェクト固有の内容に書き換える:

- **プロジェクト名・目的** をナビゲーション冒頭に記載
- **テストコマンド** を明記（例: `npm test`, `pytest`）
- **技術スタック** を 1行で記述
- 100行以内を維持すること（ARCH-005）

### 2-2. ARCHITECTURE.md のカスタマイズ

実際のディレクトリ構造を反映した内容に書き換える:

```bash
find . -maxdepth 2 -type d | grep -v node_modules | grep -v .git | sort
```

上記の出力を基に、各ディレクトリの責務を記述する。
テンプレートのディレクトリ（`agents/`, `hooks/` 等）は `.claude/` 配下に移動済みのため、
プロジェクト固有のディレクトリ構造（`src/`, `tests/`, `infra/` 等）を中心に記述する。

### 2-3. PROJECT_STATUS.md の初期化

プロジェクト開始時点の状態を記録する:

```markdown
## 現在のフェーズ
議論中

## 概要
[プロジェクト名]: [目的を1〜2文で]

## 次にやること
- [ ] 初回の議論・要件整理
- [ ] PRD 作成 (docs/prd.md)
```

### 2-4. harness.json の調整

`.claude/harness.json` は install.sh が言語別の既定値で生成している。
実際のプロジェクトのコマンドに合わせて調整する:

```bash
cat .claude/harness.json
```

- `commands.test` が実際のテストコマンドと一致しているか（package.json scripts / pyproject.toml / Makefile と照合）
- lint・typecheck・coverage 等、プロジェクトに存在するコマンドを追記する
- エージェントはコマンドをハードコードせずこのファイルを参照するため、ここが唯一の正とする

### 2-5. settings.json のフックパス検証

```bash
node .claude/hooks/arch-lint.js 2>&1
```

ARCH-004 違反（存在しないフックへの参照）があれば修正する。

### 2-6. docs/ スケルトンの補完

`docs/` 配下に不足しているファイルがあれば作成する:
- `docs/QUALITY_SCORE.md` が空テンプレートのままなら、初期スコアを記入する
- `docs/PLANS.md` に最初の実行プランエントリを追加する

---

## Step 3: 自律検証ループ

修正が完了したら、再度チェックを実行して問題がないことを確認する:

```bash
# 構造テスト
node .claude/hooks/structure-test.js

# アーキテクチャリント
echo '{}' | node .claude/hooks/arch-lint.js 2>&1

# CLAUDE.md 行数
wc -l CLAUDE.md
```

いずれかが失敗した場合は原因を特定して修正し、全チェックが通過するまでこのステップを繰り返す。

---

## Step 4: 初期コミット

すべてのチェックが通過したら、ブートストラップの完了をコミットする:

```bash
git add .
git commit -m "chore: bootstrap harness engineering scaffold

- CLAUDE.md をプロジェクト固有の内容にカスタマイズ
- ARCHITECTURE.md を実際のディレクトリ構造に合わせて更新
- PROJECT_STATUS.md を初期化
- 全構造テスト・アーキテクチャリントが通過することを確認

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## 人間へのエスカレーション基準

以下の場合のみ人間に確認する（それ以外は自律的に進める）:

| 状況 | 確認内容 |
|------|---------|
| プロジェクトの目的が不明 | 「このプロジェクトは何のためのものですか？」 |
| 技術スタックが不明 | 「主要な言語・フレームワークを教えてください」 |
| 同名ファイルが既存かつ内容が大きく異なる | 「上書きしてよいですか？」 |
| 3回修正してもチェックが通らない | エラー内容を提示して判断を仰ぐ |

---

## 完了の定義

- [ ] `node .claude/hooks/structure-test.js` が通過する
- [ ] `echo '{}' | node .claude/hooks/arch-lint.js` が違反ゼロ
- [ ] `CLAUDE.md` がプロジェクト固有の内容になっている（テンプレートのまま残っていない）
- [ ] `ARCHITECTURE.md` が実際のディレクトリ構造を反映している
- [ ] `.claude/harness.json` の commands が実プロジェクトのコマンドと一致している
- [ ] `PROJECT_STATUS.md` が初期化されている
- [ ] 初期コミットが作成されている
