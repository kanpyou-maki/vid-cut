"""レクチャー名の正規化（Design Doc 3-5-2）。人の入力とファイル名の両方に使う。"""

import re
import unicodedata

MAX_TITLE_CHARS = 100
FALLBACK_TITLE = "untitled"
"""ファイル名から題名を作れなかったとき（見える文字がない）の題名。"""

# 改行・タブ・行と段落の区切り。除くと前後の語がくっつくので、題名では空白 1 つにする
_LINE_BREAKS = re.compile(r"[\t\n\r\v\f\x1c-\x1f\x85\u2028\u2029]+")

# 画面にもファイル名にも見えず、見た目を偽れる文字:
# 制御文字、書式（双方向制御・ゼロ幅など）、行と段落の区切り
_INVISIBLE_CATEGORIES = frozenset({"Cc", "Cf", "Zl", "Zp"})


def strip_invisible(text: str) -> str:
    """NFC に正規化し、見えない文字を除く。"""
    composed = unicodedata.normalize("NFC", text)
    return "".join(ch for ch in composed if unicodedata.category(ch) not in _INVISIBLE_CATEGORIES)


def normalize_title(raw: str, *, fallback: str | None = None) -> str:
    """保存する前のレクチャー名に直す。見える文字が残らなければ fallback（なければ ValueError）。"""
    spaced = _LINE_BREAKS.sub(" ", raw)
    title = strip_invisible(spaced).strip()[:MAX_TITLE_CHARS].rstrip()
    if title:
        return title
    if fallback is None:
        raise ValueError("レクチャー名が空です（見える文字がありません）")
    return fallback
