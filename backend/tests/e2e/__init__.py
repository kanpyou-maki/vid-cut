"""E2E（Playwright。frontend/e2e/）用の起動スクリプトと偽の実装（Design Doc 6 章）。

ML と判定だけを偽の実装に差し替えて、serve と worker を起動する。本体（src）には、
差し替えのための口を置かない。ffmpeg・SQLite・API・worker・書き出しは実物を使う。
"""
