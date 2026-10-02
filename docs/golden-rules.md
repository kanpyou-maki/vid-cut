# 黄金原則 (Golden Rules)

リポジトリが常に満たすべき不変の原則。
`gc-agent` はこのファイルを参照して逸脱を検知し、修正 PR を作成する。
master・配布先プロジェクトの両方に適用される（レイアウトは同型 — ADR-004）。

## 構造ルール

| # | 原則 | 検証方法 |
|---|------|---------|
| G-01 | `CLAUDE.md` は 100行以内 | ARCH-005 (arch-lint.js) |
| G-02 | すべてのフックが `.claude/settings.json` に登録されている | ARCH-004 (arch-lint.js) |
| G-03 | `docs/adr/` に記録のないアーキテクチャ変更をコミットしない | 構造テスト |
| G-04 | `.claude/agents/` 以外にエージェント定義を置かない | ARCH-001 (arch-lint.js) |
| G-05 | `.claude/` 配下では `.claude/hooks/` 以外にフック実装を置かない | ARCH-002 (arch-lint.js) |

## 品質ルール

| # | 原則 | 検証方法 |
|---|------|---------|
| G-06 | フックのテストカバレッジは 80% 以上 | harness.json `commands.test` |
| G-07 | フックは Node.js 標準ライブラリのみ使用（外部 npm 依存禁止）| コードレビュー / style-reviewer |
| G-08 | `console.log` をフック実装に残さない | コードレビュー |
| G-09 | `.claude/rules/` のファイルは `{lang}/{category}.md` 形式 | ARCH-003 (arch-lint.js) |

## ドキュメント・グラフルール

| # | 原則 | 検証方法 |
|---|------|---------|
| G-10 | ADR は「承認済み」「提案中」「非推奨」のいずれかのステータスを持つ | 構造テスト |
| G-11 | `docs/exec-plans/active/` のプランは完了後 `completed/` へ移動する | GC エージェント |
| G-12 | `QUALITY_SCORE.md` はフェーズ完了時または GC 実行時に更新する | GC エージェント |
| G-13 | すべての docs/ 配下のドキュメントは CLAUDE.md から辿れる（孤立ノード禁止）| structure-test.js `checkDocGraph` |

## ハーネス・配布ルール

| # | 原則 | 検証方法 |
|---|------|---------|
| G-14 | エージェント・スキルはコマンドをハードコードせず `.claude/harness.json` から読む | コードレビュー / improve-harness |
| G-15 | 配布物の追加・除外は `dist-manifest.json` に宣言する（master のみ）| install.sh テスト |
| G-16 | 繰り返す摩擦は `docs/friction-log.md` に記録し、improve-harness で解消する | GC エージェント |

## GC エージェントの逸脱検知スコープ

GC エージェントは以下を定期的に確認する:
1. 上記ルールへの違反を全ファイルスキャンで検出
2. `QUALITY_SCORE.md` のスコアを最新状態に更新
3. 逸脱があれば修正差分を作成して PR をオープンする
4. 繰り返す摩擦を `docs/friction-log.md` に記録する

詳細: [.claude/agents/gc-agent.md](../.claude/agents/gc-agent.md)
