# ドキュメントテンプレート集

`doc-updater` エージェントがドキュメント作成時に参照するテンプレート。

## PRD (`docs/prd.md`)

```markdown
# PRD: {機能名}

**ステータス:** 承認済み / レビュー中
**作成日:** YYYY-MM-DD

## 1. 問題定義
### 背景
### 課題
| # | 課題 | 影響 |

### ゴール

## 2. ユーザーストーリー
- **US-01**: ...

## 3. 成功指標
| 指標 | 現状 | 目標 |

## 4. スコープ外
- ...
```

## Design Doc (`docs/design.md`)

```markdown
# Design Doc: {機能名}

**ステータス:** 承認済み / レビュー中
**作成日:** YYYY-MM-DD
**関連 PRD:** [docs/prd.md](./prd.md)

## 1. 概要
## 2. アーキテクチャ
## 3. コンポーネント設計
## 4. データモデル
## 5. トレードオフ
## 6. 未解決の問い
| # | 問い | 影響範囲 | 優先度 |
```

## ADR (`docs/adr/ADR-NNN-title.md`)

```markdown
# ADR-NNN: {短いタイトル}

**ステータス:** 提案中 / 承認済み / 非推奨 / ADR-NNN で置き換え済み
**作成日:** YYYY-MM-DD

## Context（背景）
## Decision（決定）
## Consequences（結果）
### ポジティブ
### ネガティブ
## Alternatives Considered（検討した代替案）
### 案 A: ...（採用しなかった理由）
```

## 実行プラン (`docs/exec-plans/active/PLAN-YYYYMMDD-slug.md`)

テンプレート: [exec-plans/active/_template.md](../exec-plans/active/_template.md)
