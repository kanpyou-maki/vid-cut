"""ワークスペース全体の設定: 残す発話の前後の余白（Design Doc 3-4・3-5）。

既定値は書き出しの設定（ExportSettings）が持ち、利用者が保存した値があれば、そちらを使う。
保存した値は毎回読む（worker は起動したままなので、画面で変えた値を次の書き出しから使うため）。
"""

from dataclasses import dataclass, replace

from vidcut.domain.timeline import KeepPadding
from vidcut.pipeline.export import ExportSettings
from vidcut.pipeline.ports import SettingsRepository


@dataclass(frozen=True)
class SettingsView:
    """画面に出す設定。customized は、利用者が保存した値を使っているかどうか。"""

    keep_padding: KeepPadding
    default_keep_padding: KeepPadding
    customized: bool


class SettingsService:
    def __init__(self, settings: SettingsRepository, base: ExportSettings) -> None:
        self._settings = settings
        self._base = base

    def view(self) -> SettingsView:
        stored = self._settings.keep_padding()
        default = KeepPadding(
            before_ms=self._base.pad_before_ms,
            after_ms=self._base.pad_after_ms,
            after_sentence_ms=self._base.pad_after_sentence_ms,
        )
        return SettingsView(
            keep_padding=stored or default,
            default_keep_padding=default,
            customized=stored is not None,
        )

    def save_keep_padding(self, padding: KeepPadding) -> SettingsView:
        self._settings.save_keep_padding(padding)
        return self.view()

    def reset_keep_padding(self) -> SettingsView:
        self._settings.clear_keep_padding()
        return self.view()

    def export_settings(self) -> ExportSettings:
        """いまの書き出しの設定。フレームレートは変えられない（中間素材と同じ値にそろえてある）。"""
        stored = self._settings.keep_padding()
        if stored is None:
            return self._base
        return replace(
            self._base,
            pad_before_ms=stored.before_ms,
            pad_after_ms=stored.after_ms,
            pad_after_sentence_ms=stored.after_sentence_ms,
        )
