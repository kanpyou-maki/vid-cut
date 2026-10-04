from dataclasses import dataclass, field

from vidcut.domain.timeline import KeepPadding
from vidcut.pipeline.export import ExportSettings
from vidcut.services.settings import SettingsService

BASE = ExportSettings(fps=30, pad_before_ms=150, pad_after_ms=250, pad_after_sentence_ms=500)
DEFAULT = KeepPadding(before_ms=150, after_ms=250, after_sentence_ms=500)
CHOSEN = KeepPadding(before_ms=100, after_ms=300, after_sentence_ms=800)


@dataclass
class MemorySettings:
    stored: KeepPadding | None = None
    calls: list[str] = field(default_factory=list)

    def keep_padding(self) -> KeepPadding | None:
        self.calls.append("read")
        return self.stored

    def save_keep_padding(self, padding: KeepPadding) -> None:
        self.stored = padding

    def clear_keep_padding(self) -> None:
        self.stored = None


class TestSettingsService:
    def test_uses_the_defaults_until_something_is_saved(self) -> None:
        view = SettingsService(MemorySettings(), BASE).view()
        assert (view.keep_padding, view.default_keep_padding, view.customized) == (
            DEFAULT,
            DEFAULT,
            False,
        )

    def test_saved_padding_replaces_the_defaults(self) -> None:
        service = SettingsService(MemorySettings(), BASE)

        view = service.save_keep_padding(CHOSEN)

        assert (view.keep_padding, view.default_keep_padding, view.customized) == (
            CHOSEN,
            DEFAULT,
            True,
        )
        assert service.view() == view

    def test_reset_returns_to_the_defaults(self) -> None:
        repo = MemorySettings(stored=CHOSEN)
        service = SettingsService(repo, BASE)

        view = service.reset_keep_padding()

        assert (view.keep_padding, view.customized) == (DEFAULT, False)
        assert repo.stored is None

    def test_export_settings_keep_the_frame_rate_and_take_the_saved_padding(self) -> None:
        service = SettingsService(MemorySettings(stored=CHOSEN), BASE)
        assert service.export_settings() == ExportSettings(
            fps=30, pad_before_ms=100, pad_after_ms=300, pad_after_sentence_ms=800
        )

    def test_export_settings_are_the_base_until_something_is_saved(self) -> None:
        assert SettingsService(MemorySettings(), BASE).export_settings() == BASE

    def test_reads_the_stored_value_every_time(self) -> None:
        # worker は起動したままなので、書き出しのたびに読み直す
        repo = MemorySettings()
        service = SettingsService(repo, BASE)
        service.export_settings()
        repo.stored = CHOSEN
        assert service.export_settings().pad_after_sentence_ms == 800
        assert repo.calls == ["read", "read"]
