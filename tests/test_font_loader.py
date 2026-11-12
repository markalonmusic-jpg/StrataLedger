import io
import zipfile

import pytest
from urllib.error import URLError

from modules import font_loader


def test_extracts_only_required_inter_fonts(tmp_path, monkeypatch):
    archive_buffer = io.BytesIO()
    with zipfile.ZipFile(archive_buffer, "w") as archive:
        for filename in font_loader.FONT_FILES:
            archive.writestr(f"extras/ttf/{filename}", filename.encode())
        archive.writestr("OFL.txt", b"font license")

    monkeypatch.setattr(font_loader, "FONT_DIR", str(tmp_path))
    font_loader._extract_font_files(archive_buffer.getvalue(), str(tmp_path))

    assert {path.name for path in tmp_path.iterdir()} == {
        *font_loader.FONT_FILES,
        "OFL.txt",
    }
    for filename in font_loader.FONT_FILES:
        assert (tmp_path / filename).read_bytes() == filename.encode()


def test_inter_is_not_downloaded_when_already_registered(monkeypatch):
    monkeypatch.setattr(font_loader, "_registered_families", lambda: {"Inter", "Segoe UI"})
    monkeypatch.setattr(
        font_loader,
        "_download_and_extract_fonts",
        lambda: pytest.fail("font archive should not be downloaded"),
    )

    assert font_loader.ensure_inter_font()


def test_download_failure_uses_fallback(monkeypatch, tmp_path, caplog):
    monkeypatch.setattr(font_loader, "FONT_DIR", str(tmp_path))
    monkeypatch.setattr(font_loader, "_registered_families", lambda: {"Segoe UI"})

    def fail_download():
        raise URLError("offline")

    monkeypatch.setattr(font_loader, "_download_and_extract_fonts", fail_download)

    assert not font_loader.ensure_inter_font()
    assert "using Segoe UI" in caplog.text
