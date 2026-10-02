# review-loop スキル — Ralph Wiggum ループ

実装完了後、PR 作成前に全レビュアーを通過させるオーケストレーション手順。
**全レビュアーの合格を得るまでループを抜けられない。**

参考: [docs/golden-rules.md](../../../docs/golden-rules.md)（審査基準の原典）。設計の経緯は master の docs/design.md § 7 と ADR-003 を参照。

---

## パイプライン全体図

```
実装完了
  │
  ▼
[Stage 0] self-reviewer
  │ BLOCK ──→ 修正 ──→ Stage 0 に戻る
  │ PASS
  ▼
[Stage 1] arch-reviewer + style-reviewer + test-reviewer（並行）
  │ いずれか BLOCK ──→ 全フィードバックを集約 ──→ 修正 ──→ Stage 1 に戻る
  │ 全 PASS
  ▼
[Stage 2] security-reviewer + docs-reviewer（並行）
  │ いずれか BLOCK ──→ フィードバック ──→ 修正 ──→ Stage 2 に戻る
  │ 全 PASS（WARNING は許容）
  ▼
PR 作成
```

---

## Stage 0: 自己評価

```
Task(
  description: "self-reviewer: 変更内容を批判的に自己評価する",
  agent: "self-reviewer"
)
```

- 判定が **PASS** → Stage 1 へ進む
- 判定が **BLOCK** → レポートの指摘を修正し、Stage 0 を再実行する

---

## Stage 1: 構造・品質・テスト審査（並行）

3つのレビュアーを**並行**で実行する。

```
Task(arch-reviewer) ──┐
Task(style-reviewer) ──┼──→ 結果を集約
Task(test-reviewer) ──┘
```

**集約ルール:**
- 全員 PASS → Stage 2 へ進む
- 1人でも BLOCK → **全員の** フィードバックを一括収集し、修正してから Stage 1 を再実行する
  - 理由: 複数の指摘を個別対応すると、修正が別の指摘を生む場合があるため

**Stage 1 再実行時の注意:**
- arch-reviewer が PASS 済みでも、style/test の修正がアーキテクチャに影響しうるため、全員を再実行する

---

## Stage 2: セキュリティ・ドキュメント審査（並行）

```
Task(security-reviewer) ──┐
Task(docs-reviewer) ────┘──→ 結果を集約
```

**集約ルール:**
- security-reviewer: PASS または WARNING → 通過。BLOCK → 修正後 Stage 2 再実行
- docs-reviewer: PASS → 通過。BLOCK → 修正後 Stage 2 再実行
- WARNING は PR の説明欄に記載する

---

## PR 作成

全ステージを通過したら PR を作成する。

```bash
gh pr create \
  --title "[変更の概要]" \
  --body "$(cat <<'EOF'
## 変更内容
[説明]

## レビュー通過記録
- Stage 0 (self-reviewer): ✅ PASS
- Stage 1 (arch/style/test): ✅ 全 PASS
- Stage 2 (security/docs): ✅ PASS（WARNING があれば記載）

## セキュリティ補足
[security-reviewer が WARNING を出した場合の詳細]
EOF
)"
```

---

## PR のタイムライン指針

**修正は安価、待機は高コスト。** PR はオープンから短期間でクローズすることを目指す。

| 状態 | 対処 |
|------|------|
| Stage 1/2 で軽微な指摘のみ | 即修正してマージする |
| 複数の大きな指摘が出た | スコープを分割して小さな PR に切り出す |
| テストフレークで足止め | WARNING として記録しマージし、フォローアップ PR でフレークを修正する |
| PR が 1日以上停滞 | スコープが大きすぎる可能性がある。分割を検討する |

**フレークによる無期限ブロックは避ける。** `test-reviewer` が WARNING を出したフレークは PR の説明欄に記録し、マージを続行してよい。

---

## 摩擦シグナルの処理

同一ステージで **3回以上 BLOCK** が続くとき、それは「もっと頑張れ」ではなく**リポジトリ自体の改善シグナル**として扱う。エスカレーションと改善 PR を同時に進める。

### 根本原因の分類

| 繰り返しパターン | 根本原因 | 改善対象 |
|----------------|---------|---------|
| 同じ ARCH 規則を繰り返し違反する | 自動検出の漏れ | `.claude/hooks/arch-lint.js` にチェックを追加 |
| 同じスタイル問題が繰り返し出る | ガードレール不足 | `.claude/hooks/arch-lint.js` で機械的に強制する |
| 同じ種類のエッジケースを常に見落とす | テスト指針の不足 | `.claude/agents/test-reviewer.md` または `.claude/rules/*/testing.md` を更新 |
| ドキュメントの同じ整合性問題が出る | ドキュメント構造の問題 | `.claude/agents/docs-reviewer.md` または `docs/` 構造を改善 |
| セキュリティの同じ指摘が繰り返される | ガードレール不足 | `.claude/hooks/arch-lint.js` に静的チェックを追加 |

### 処理フロー

1. BLOCK のパターンを上表で分類する
2. **`docs/friction-log.md` にエントリを追加する**（FRIC-NNN。何が・なぜ繰り返すか・改善候補）
3. **実装の修正**（当面の問題を解決）を先に進め、ハーネスの改善は `improve-harness` スキル（`.claude/skills/improve-harness/SKILL.md`）で行う
4. 改善が master にも有効な汎用的なものであれば、`sync-upstream` スキルで master への還元を提案する
5. 改善後、元のタスクを再実行して摩擦が解消されたことを確認する

**原則: 摩擦はリポジトリを改善するチャンスである。**

---

## 使用するエージェント

| エージェント | ステージ | 役割 |
|-------------|---------|------|
| `self-reviewer` | Stage 0 | 実装の自己批判的評価 |
| `arch-reviewer` | Stage 1 | アーキテクチャ規則検証 |
| `style-reviewer` | Stage 1 | コーディングスタイル検証 |
| `test-reviewer` | Stage 1 | テスト品質・カバレッジ検証 |
| `security-reviewer` | Stage 2 | セキュリティ脆弱性検証 |
| `docs-reviewer` | Stage 2 | ドキュメント整合性検証 |
