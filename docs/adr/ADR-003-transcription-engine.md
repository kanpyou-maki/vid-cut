# ADR-003: 文字起こしは mlx-whisper、位置合わせは WhisperX を使う

**ステータス:** 提案中（スパイク S-2・S-3 の結果で確定する）
**作成日:** 2026-10-03

## Context（背景）

必要なのは、日本語の文字起こしと、文字単位の時刻（テキスト編集とカット、将来のテロップ用）と、確信度（要確認の印）である。
環境は Apple Silicon の Mac で、費用をかけずローカルで完結させたい。

プロトタイプでは whisper.cpp（ggml-medium）で 6 分の音声を約 70 秒で処理した。
Whisper はフィラーを省いて書き起こす癖があるため、ヒント文にフィラーを含める対策を取る。

## Decision（決定）

- 文字起こしは **mlx-whisper**（モデルは large-v3-turbo を第一候補）。無音で区切ったチャンクごとに実行する
  - トークンごとの確率を確信度として使う
- 文字単位の時刻は **WhisperX の位置合わせ**（日本語は wav2vec2 の CTC）で付ける。合わせ込みのスコアも保存する
- どちらも `pipeline/ports.py` の `Transcriber` / `Aligner` の背後に置き、差し替えられるようにする

## Consequences（結果）

### ポジティブ

- Apple Silicon の GPU（MLX）で large 系のモデルを実用的な速度で動かせる見込み
- 文字単位の時刻が取れるので、テキストの選択範囲をそのままカット区間にできる

### ネガティブ

- WhisperX は PyTorch に依存し、セットアップが重い。Apple Silicon の GPU（MPS）では動かない部分があり、CPU 実行になる可能性がある
- 2 つのモデルをメモリに載せる。worker は 1 件ずつ処理するので許容範囲と見込む

## Alternatives Considered（検討した代替案）

### 案 A: whisper.cpp

既にローカルにあり、速度も確認済み。Python からはサブプロセスかバインディング経由になり、トークンの確率の取り出しが mlx-whisper より手間がかかる。
スパイク S-2 で mlx-whisper の精度か速度が明らかに劣れば、こちらにする。

### 案 B: faster-whisper（CTranslate2）

kickoff で名前が挙がっていたが、Mac では GPU を使えず CPU 実行になり遅い。採用しない。

### 案 C: Whisper の単語タイムスタンプだけを使う（位置合わせなし）

依存は軽くなるが、日本語では時刻の精度が粗く、カット点がずれる。採用しない。
