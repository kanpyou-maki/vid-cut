import pytest

from vidcut.domain.titles import MAX_TITLE_CHARS, normalize_title, strip_invisible


class TestStripInvisible:
    def test_composes_decomposed_kana(self) -> None:
        # macOS のファイル名は濁点が分かれた形（NFD）で来ることがある
        assert strip_invisible("ガイド") == "ガイド"

    @pytest.mark.parametrize(
        "char",
        [
            "‮",  # 右から左への上書き（Cf）
            "​",  # ゼロ幅スペース（Cf）
            "﻿",  # BOM（Cf）
            " ",  # 行の区切り（Zl）
            " ",  # 段落の区切り（Zp）
            "\x00",
            "\n",
            "\x9f",  # C1 の制御文字（Cc）
        ],
    )
    def test_removes_characters_that_do_not_show(self, char: str) -> None:
        assert strip_invisible(f"a{char}b") == "ab"

    def test_keeps_visible_spaces_and_symbols(self) -> None:
        assert strip_invisible("S05-12 環境構築（前編）") == "S05-12 環境構築（前編）"


class TestNormalizeTitle:
    def test_keeps_a_plain_title(self) -> None:
        assert normalize_title("S05-12 環境構築") == "S05-12 環境構築"

    def test_trims_surrounding_whitespace(self) -> None:
        assert normalize_title("  題名　 ") == "題名"

    def test_removes_invisible_characters_and_composes(self) -> None:
        assert normalize_title("‮ガイド​") == "ガイド"

    def test_shortens_long_titles(self) -> None:
        assert normalize_title("あ" * 300) == "あ" * MAX_TITLE_CHARS

    def test_shortened_title_does_not_end_with_whitespace(self) -> None:
        title = normalize_title("あ" * (MAX_TITLE_CHARS - 1) + " い")
        assert title == "あ" * (MAX_TITLE_CHARS - 1)

    @pytest.mark.parametrize("raw", ["", "   ", "​‮", "\n"])
    def test_rejects_titles_with_nothing_visible(self, raw: str) -> None:
        with pytest.raises(ValueError, match="レクチャー名"):
            normalize_title(raw)

    def test_uses_the_fallback_when_nothing_is_visible(self) -> None:
        assert normalize_title("​", fallback="untitled") == "untitled"
