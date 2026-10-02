# Skill: sync-downstream — マスターの更新をプロジェクトへ反映

`claude-config-master` の最新改善をこのプロジェクトの `.claude/` へ取り込む。
master とこのプロジェクトは `.claude/` 配下が**同型レイアウト**のため、対応ファイルはパス変換なしの 1:1 で比較・コピーできる。

## トリガー

「マスターの更新を取り込んで」「マスターと同期して」と言われたとき。
または `install.sh update` が CHANGED (skipped) を報告したとき（変更ファイルのマージはこのスキルの仕事）。

---

## 手順

### 1. マスターパスを確認する

```bash
MASTER=$(cat .claude/master-path 2>/dev/null || cat ~/.claude/master-path 2>/dev/null || echo "")
if [[ -z "$MASTER" || ! -d "$MASTER" ]]; then
  echo "ERROR: master-path が未設定または無効です"
  echo "設定方法: echo \"/path/to/claude-config-master\" > .claude/master-path"
  exit 1
fi
echo "Master: $MASTER"
```

**機械的に取り込める分（新規ファイル・hooks 更新）は install.sh update に任せるのが速い:**

```bash
MASTER=$(cat .claude/master-path 2>/dev/null || cat ~/.claude/master-path)
LANG_CHOICE=$(node -pe "require('./.claude/harness.json').language" 2>/dev/null || echo typescript)
bash "$MASTER/install.sh" update "$LANG_CHOICE" "$(pwd)"
```

以降の手順は、install.sh update が「CHANGED (skipped)」と報告した**変更ファイルのマージ**に使う。

### 2. 差分を確認する

```bash
MASTER=$(cat .claude/master-path 2>/dev/null || cat ~/.claude/master-path)

for dir in agents hooks rules skills; do
  echo "=== .claude/$dir vs $MASTER/.claude/$dir ==="
  diff -rq ".claude/$dir/" "$MASTER/.claude/$dir/" 2>/dev/null || true
done
```

差分を次の3種類に分類する:

| 種類 | 見分け方 | 対処 |
|------|---------|------|
| **新規** | マスターに存在するがプロジェクトにない | コピーして取り込む（install.sh update が自動処理済みのはず）|
| **変更** | 両方に存在して内容が異なる | カスタマイズを保持しつつマージ（下記参照）|
| **プロジェクト固有** | プロジェクトにのみ存在する / manifest の exclude 対象（harness.json 等）| スキップ |

### 3. 変更ファイルをマージする

変更があるファイルについて、以下の手順でマージする:

1. マスター版とプロジェクト版の両方を Read する
2. プロジェクト固有のカスタマイズ（app 名・固有フロー・tech stack 固有の設定等）を特定する
3. マスターの改善部分を取り込み、プロジェクト固有部分を保持した新バージョンを作成する
4. **変更内容を人間に提示して確認を求める**こと

**hooks/*.js の扱い:**
hooks はプロジェクト固有のカスタマイズをほとんど含まないため、
マスター版で上書きしてよい（install.sh update は常に上書きする）。ただし確認は求めること。

### 4. 検証してコミットする

```bash
# 取り込んだ設定が壊れていないことを確認
node .claude/hooks/structure-test.js
echo '{}' | node .claude/hooks/arch-lint.js 2>&1

git add -A
git commit -m "$(cat <<EOF
chore: sync from master $(date +%Y-%m-%d)

Co-Authored-By: sync-downstream-skill <noreply@anthropic.com>
EOF
)"
```

---

## 注意事項

- CLAUDE.md / ARCHITECTURE.md / PROJECT_STATUS.md はプロジェクト固有ファイルのため**スキップ**する
- `.claude/harness.json` / `.claude/master-path` / settings.local.json はプロジェクト固有のため**上書きしない**
- マージ判断が難しい場合は人間に委ねること
