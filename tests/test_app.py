"""Tests for the DLPX Flet app backend helpers."""

import pytest
import flet as ft
from main import (
    FormatInfo,
    SearchResult,
    DownloadTask,
    human_size,
    parse_formats,
    smart_pick,
)


# ── human_size ────────────────────────────────────────


class TestHumanSize:
    def test_none(self):
        assert human_size(None) == "-"

    def test_zero(self):
        assert human_size(0) == "-"

    def test_bytes(self):
        assert human_size(500) == "500.0 B"

    def test_kilobytes(self):
        assert human_size(2048) == "2.0 KB"

    def test_megabytes(self):
        assert human_size(5 * 1024 * 1024) == "5.0 MB"

    def test_gigabytes(self):
        assert human_size(3 * 1024 ** 3) == "3.0 GB"

    def test_terabytes(self):
        assert human_size(2 * 1024 ** 4) == "2.0 TB"


# ── parse_formats ─────────────────────────────────────


def _make_yt_format(**kw):
    base = {
        "format_id": "22",
        "ext": "mp4",
        "url": "https://example.com/v.mp4",
        "vcodec": "avc1",
        "acodec": "mp4a",
        "height": 720,
        "resolution": "1280x720",
        "fps": 30,
        "filesize": 1_000_000,
        "format_note": "720p",
        "protocol": "https",
    }
    base.update(kw)
    return base


class TestParseFormats:
    def test_empty_info(self):
        assert parse_formats({}) == []

    def test_no_url_skipped(self):
        info = {"formats": [{"format_id": "1", "ext": "mp4"}]}
        assert parse_formats(info) == []

    def test_single_progressive(self):
        info = {"formats": [_make_yt_format()]}
        result = parse_formats(info)
        assert len(result) == 1
        f = result[0]
        assert f.format_id == "22"
        assert f.ext == "mp4"
        assert f.height == 720
        assert f.is_progressive is True
        assert f.is_audio_only is False

    def test_audio_only(self):
        info = {"formats": [_make_yt_format(vcodec="none", acodec="mp4a", height=0)]}
        result = parse_formats(info)
        assert len(result) == 1
        assert result[0].is_audio_only is True
        assert result[0].is_progressive is False

    def test_video_only(self):
        info = {"formats": [_make_yt_format(acodec="none")]}
        result = parse_formats(info)
        assert len(result) == 1
        assert result[0].is_progressive is False
        assert result[0].is_audio_only is False

    def test_sorted_progressive_first(self):
        info = {
            "formats": [
                _make_yt_format(format_id="1", vcodec="avc1", acodec="none", height=1080),
                _make_yt_format(format_id="2", vcodec="avc1", acodec="mp4a", height=720),
            ]
        }
        result = parse_formats(info)
        assert result[0].format_id == "2"  # progressive comes first
        assert result[1].format_id == "1"

    def test_sorted_by_height(self):
        info = {
            "formats": [
                _make_yt_format(format_id="a", height=480),
                _make_yt_format(format_id="b", height=1080),
                _make_yt_format(format_id="c", height=720),
            ]
        }
        result = parse_formats(info)
        assert [f.format_id for f in result] == ["b", "c", "a"]


# ── smart_pick ────────────────────────────────────────


class TestSmartPick:
    def test_empty(self):
        assert smart_pick([]) is None

    def test_prefers_progressive(self):
        formats = [
            FormatInfo("1", "mp4", "1080p", 1080, None, "-", False, False),
            FormatInfo("2", "mp4", "720p", 720, None, "-", True, False),
        ]
        picked = smart_pick(formats)
        assert picked is not None
        assert picked.format_id == "2"

    def test_prefers_mp4(self):
        formats = [
            FormatInfo("1", "webm", "1080p", 1080, None, "-", True, False),
            FormatInfo("2", "mp4", "720p", 720, None, "-", True, False),
        ]
        picked = smart_pick(formats)
        assert picked is not None
        assert picked.format_id == "2"

    def test_highest_resolution(self):
        formats = [
            FormatInfo("1", "mp4", "480p", 480, None, "-", True, False),
            FormatInfo("2", "mp4", "1080p", 1080, None, "-", True, False),
            FormatInfo("3", "mp4", "720p", 720, None, "-", True, False),
        ]
        picked = smart_pick(formats)
        assert picked is not None
        assert picked.format_id == "2"

    def test_fallback_non_progressive(self):
        formats = [
            FormatInfo("1", "mp4", "1080p", 1080, None, "-", False, False),
        ]
        picked = smart_pick(formats)
        assert picked is not None
        assert picked.format_id == "1"

    def test_audio_only_fallback(self):
        formats = [
            FormatInfo("1", "m4a", "audio", 0, None, "-", False, True),
        ]
        picked = smart_pick(formats)
        assert picked is not None
        assert picked.format_id == "1"


# ── Data model defaults ──────────────────────────────


class TestDownloadTask:
    def test_defaults(self):
        task = DownloadTask(url="https://example.com", title="Test")
        assert task.status == "pending"
        assert task.progress == 0.0
        assert task.error == ""
        assert task.format_id is None


class TestSearchResult:
    def test_creation(self):
        r = SearchResult(title="Test", url="https://example.com", duration="3:45", source="youtube")
        assert r.title == "Test"
        assert r.source == "youtube"


# ── Flet API compatibility ────────────────────────────
# These tests verify that all Flet attributes used in main.py
# exist in the installed Flet version, catching breaking API
# changes before a 20-minute APK build cycle.


class TestFletControls:
    """Verify Flet control classes used in main.py are importable."""

    @pytest.mark.parametrize("name", [
        "AlertDialog", "Card", "CircleAvatar", "Column", "Container",
        "Divider", "Dropdown", "ElevatedButton", "Icon", "IconButton",
        "ListTile", "ListView", "NavigationBar", "NavigationBarDestination",
        "OutlinedButton", "Page", "ProgressBar", "Row", "SafeArea",
        "SnackBar", "Text", "TextButton", "TextField", "Theme",
    ])
    def test_control_exists(self, name):
        assert hasattr(ft, name), f"ft.{name} missing"
        assert callable(getattr(ft, name))

    def test_dropdown_option(self):
        assert hasattr(ft.dropdown, "Option")
        assert callable(ft.dropdown.Option)

    def test_ft_run(self):
        assert hasattr(ft, "run")
        assert callable(ft.run)


class TestFletEnums:
    """Verify Flet enum constants used in main.py resolve correctly."""

    @pytest.mark.parametrize("attr", [
        "Colors.RED", "Colors.BLUE", "Colors.GREEN", "Colors.GREY",
        "Colors.ORANGE", "Colors.WHITE",
    ])
    def test_color(self, attr):
        obj = ft
        for part in attr.split("."):
            obj = getattr(obj, part)

    @pytest.mark.parametrize("attr", [
        "Icons.CHECK_CIRCLE", "Icons.CLEAR", "Icons.DELETE_SWEEP",
        "Icons.DOWNLOAD", "Icons.DOWNLOADING", "Icons.ERROR",
        "Icons.FOLDER", "Icons.HELP", "Icons.HOME",
        "Icons.HOURGLASS_EMPTY", "Icons.INFO", "Icons.LINK",
        "Icons.LIST", "Icons.REFRESH", "Icons.SEARCH",
        "Icons.SETTINGS", "Icons.VIDEO_LIBRARY",
    ])
    def test_icon(self, attr):
        obj = ft
        for part in attr.split("."):
            obj = getattr(obj, part)

    @pytest.mark.parametrize("attr", [
        "FontWeight.BOLD",
        "TextOverflow.ELLIPSIS",
        "ScrollMode.AUTO",
        "ThemeMode.DARK",
        "CrossAxisAlignment.CENTER",
        "MainAxisAlignment.SPACE_BETWEEN",
    ])
    def test_enum_constant(self, attr):
        obj = ft
        for part in attr.split("."):
            obj = getattr(obj, part)


class TestFletAlignment:
    """Verify Alignment class API (was ft.alignment.center, now ft.Alignment.CENTER)."""

    def test_alignment_center(self):
        assert hasattr(ft, "Alignment")
        assert hasattr(ft.Alignment, "CENTER")


class TestFletPadding:
    """Verify Padding class methods (was ft.padding.*, now ft.Padding.*)."""

    def test_padding_only(self):
        result = ft.Padding.only(top=10, bottom=5)
        assert result is not None

    def test_padding_symmetric(self):
        result = ft.Padding.symmetric(horizontal=16, vertical=8)
        assert result is not None

    def test_padding_only_all_kwargs(self):
        result = ft.Padding.only(top=20, left=16, right=16, bottom=8)
        assert result is not None
