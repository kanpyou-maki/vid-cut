# ADR-000: claude-config-master ハーネスの採用

**ステータス:** 承認済み
**作成日:** 2026-10-03

## Context（背景）

Claude Code によるエージェントファースト開発を行うにあたり、
ハーネス（hooks / rules / agents / skills）をゼロから構築するコストを避けたい。

## Decision（決定）

claude-config-master のハーネス設定一式を install.sh で導入する。

- 設定は `.claude/` 配下に同型レイアウトで配置される
- コマンド定義は `.claude/harness.json` に集約する
- master への改善還元は sync-upstream、master からの更新取り込みは install.sh update / sync-downstream で行う

## Consequences（帰結）

- アーキテクチャ規則（ARCH-001〜006）が機械的に強制される
- 以降のアーキテクチャ判断はこのディレクトリに ADR として記録すること
