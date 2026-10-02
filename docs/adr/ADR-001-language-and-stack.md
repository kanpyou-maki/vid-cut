# ADR-001: 実装言語と技術スタック（Python パイプライン + TypeScript UI）

**ステータス:** 承認済み
**作成日:** 2026-10-03

## Context（背景）

vid-cut は、Udemy 用に録画した mov から無音・フィラー・言い直しを検出してカットし、
Premiere XML（FCP7 xmeml）として書き出すローカルアプリである（[kickoff](../references/kickoff.md)）。

処理の中核は次の 3 つ。

1. **音声 ML**: 日本語の文字起こし（mlx-whisper / Faster-Whisper）、文字単位の位置合わせ（WhisperX = wav2vec2）、
   VAD（Silero）、それぞれの確信度
2. **メディア処理**: ffmpeg による音声抽出・可変フレームレートの固定化・MP4 書き出し、Premiere XML 生成、`claude -p` の呼び出し
3. **編集 UI**: 動画プレビュー、文字起こしを Google ドキュメントの感覚で選択・削除する画面、波形タイムライン

ハーネスは Python / TypeScript 用が用意されている。ユーザーからは「より適性のある言語があればその二つに拘らなくてよい」と指示を受けている。

## Decision（決定）

- **バックエンド（解析パイプライン + ローカル API）: Python**
  - パッケージ管理は uv。ML 系ライブラリとの互換性のため Python 3.12 に固定する（ローカルの既定は 3.13）
  - API は FastAPI。パイプラインの各段は API から独立して CLI からも実行できるようにする
- **フロントエンド（編集 UI）: TypeScript + React + Vite**
  - 波形は wavesurfer.js 等の既存ライブラリを優先して検討する
- **デスクトップ化（Tauri = Rust）は保留**。ローカル Web アプリで不便が出たときに改めて ADR を起こす
- ハーネスは `language: both` のまま使う（`.claude/rules/python` と `.claude/rules/typescript` の両方を適用）

## Consequences（結果）

### ポジティブ

- 音声 ML ライブラリを直接呼べる。プロトタイプ（`docs/references/prototype/udemy_cut.py`）の知見とコードをそのまま移植できる
- 文字起こしを文書として編集する UI は、Web 技術の資産（contenteditable 系エディタ、波形ライブラリ）が最も厚い
- 既存のハーネス（rules / reviewers / quality-gate）がそのまま機能する

### ネガティブ

- 2 言語構成になる。境界（API スキーマ）の型を両側で維持する必要がある → OpenAPI から TS 型を生成する方向で設計フェーズで決める
- 配布形態はローカル Web アプリなので、起動手順がネイティブアプリより一手多い（ユーザー本人のみが使う前提では許容）
- PyTorch 系（WhisperX / Silero）の依存は重い。初回セットアップに時間がかかる

## Alternatives Considered（検討した代替案）

### 案 A: Swift ネイティブ macOS アプリ（AVFoundation + WhisperKit）

可変フレームレート素材の扱いと動画プレビューは AVFoundation が最も強く、Apple Silicon 向けの最適化も効く。
しかし、日本語の文字単位の位置合わせ（wav2vec2 + CTC）に相当する成熟した実装がなく、自前実装になる。
また、Swift 用のハーネス（rules / reviewer / quality-gate）がないため、ゼロから整備するコストがかかる。採用しない。

### 案 B: Rust + Tauri（whisper.cpp バインディング）

参考 OSS の RoughCut がこの構成である。配布しやすく軽量だが、WhisperX 相当の位置合わせと Silero VAD を Rust 側で揃えるのは難しく、
結局 Python をサイドカーとして抱えることになる。UI 層だけを Tauri で包む可能性は残す（デスクトップ化の保留として記録した）。

### 案 C: Python 単独（Streamlit / Gradio 等の UI）

最も早く動くが、「テキストを選択・削除すると動画も同時にカットされる」編集体験と、波形上の区間の色分け表示を
作り込むには表現力が足りない。採用しない。

### 案 D: TypeScript 単独（Electron + whisper.cpp / transformers.js）

ML 部分の日本語の精度と位置合わせの品質が Python 版に及ばず、プロトタイプで得た知見も移植しづらい。採用しない。
