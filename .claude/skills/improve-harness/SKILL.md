# Skill: improve-harness — ハーネス自己改善ループ

エージェント設定（`.claude/` 配下の agents / hooks / rules / skills）を**エージェント自身が改善する**ための手順。
`docs/friction-log.md` に蓄積した摩擦を入力とし、設定改善を出力する閉ループを回す。

```
作業中の摩擦
  ↓ review-loop / gc-agent / 任意のエージェントが記録
docs/friction-log.md（FRIC-NNN）
  ↓ このスキルが消費
.claude/ 配下の設定改善（+ 検証）
  ↓ 汎用的なら
sync-upstream → master → 他プロジェクトへ sync-downstream
```

## トリガー

- 「ハーネスを改善して」「摩擦ログを処理して」と言われたとき
- gc-agent が「open な摩擦エントリが溜まっている」と報告したとき
- review-loop で同一ステージの BLOCK が 3回以上続いたとき（当面の実装修正と並行して起動）

---

## 手順

### 1. 摩擦の収集

```bash
# open な摩擦エントリを列挙
grep -B1 -A6 "Status:.*open" docs/friction-log.md
```

摩擦ログにエントリがない場合でも、直近の作業に以下の兆候があれば新規エントリとして記録してから進む:
- 同じ種類の修正を 2回以上繰り返した
- エージェントの指示とリポジトリの実態が食い違っていた
- 必要なコマンド・ドキュメントが見つからず探し回った

### 2. 改善先の分類

各摩擦を **1つの改善先** に分類する。判断基準は「ルールのエスカレーション原則」（[core-beliefs.md](../../../docs/design-docs/core-beliefs.md)）:

| 摩擦の性質 | 改善先 | 例 |
|-----------|--------|-----|
| 機械的に検出できる違反 | `.claude/hooks/arch-lint.js` に ARCH-NNN を追加 | 配置規則・命名規則・参照整合性 |
| エージェントの手順・判断の曖昧さ | 該当する `.claude/agents/*.md` を具体化 | チェック漏れ・判定基準の欠落 |
| 繰り返し使う手順の欠落 | `.claude/skills/` に新スキル追加 | 定型オペレーションの手順化 |
| 常時適用すべき規約の欠落 | `.claude/rules/{lang}/*.md` に追記 | コーディング規約・セキュリティ |
| コマンドの不一致・ハードコード | `.claude/harness.json` を修正 | テストコマンドの変更 |
| 知識の欠落（なぜ・背景） | `docs/`（ADR・design-docs）に記述 | 設計判断の理由 |

**原則: 機械化できるものは機械化する。ドキュメントだけに留まるルールは腐敗する。**

### 3. 改善の実装

- hooks を変更する場合は **TDD**（`test/` にテストを先に追加 → 実装）。master ではテストが同梱されている。配布先プロジェクトに test/ がない場合は、変更後に `node --check` と手動実行（`echo '{}' | node .claude/hooks/arch-lint.js`）で検証する
- agents / skills / rules の変更は、**変更後のファイルだけを読んだ将来のエージェントが正しく動けるか**を基準に書く（このセッションの文脈を前提にしない）
- 1回の改善は 1〜3 個の摩擦に絞る。大きくしすぎない

### 4. 検証

```bash
# ハーネス自体の整合性
node .claude/hooks/structure-test.js
echo '{}' | node .claude/hooks/arch-lint.js 2>&1

# master またはテストのあるプロジェクトでは単体テストも実行
bash -c "$(node -pe "require('./.claude/harness.json').commands.test")" 2>&1 || true
```

**改善が実際に摩擦を防ぐことを確認する:** 可能なら摩擦を再現する操作を行い、新しいガードレールが検出・防止することを確かめる。

### 5. 摩擦ログの更新

解消したエントリの Status を更新する:

```markdown
- **Status:** resolved (<コミットハッシュ or PR>)
```

### 6. 上流への還元判断

改善が **このプロジェクト固有でない**（プロジェクト名・固有フローを含まない）場合:

1. `sync-upstream` スキル（[SKILL.md](../sync-upstream/SKILL.md)）で master への PR を作成する
2. PR 本文に対応する FRIC-NNN を引用する（どの摩擦への恒久対策かを master 側でも追跡できるように）

master 自身でこのスキルを実行している場合は、コミット後に他プロジェクトへの `install.sh update` / sync-downstream を案内する。

---

## エスカレーション基準

| 状況 | 対応 |
|------|------|
| 改善が ARCH 規則・黄金原則そのものの変更を伴う | ADR を起草して人間の承認を得る |
| 同じ摩擦への改善が 2回失敗している | アプローチを人間に相談する |
| 改善対象が settings.json のパーミッション | 人間の確認を必須とする |

## 参考

- [docs/friction-log.md](../../../docs/friction-log.md) — 入力となる摩擦ログ
- [docs/design-docs/core-beliefs.md](../../../docs/design-docs/core-beliefs.md) — ルールのエスカレーション原則
- [.claude/skills/sync-upstream/SKILL.md](../sync-upstream/SKILL.md) — master への還元
- [.claude/skills/review-loop/SKILL.md](../review-loop/SKILL.md) — 摩擦シグナルの発生源
