import subprocess

from agent import clipboard
from agent.clipboard import (
    WL_PASTE,
    XCLIP,
    clipboard_has_image,
    find_clipboard_tool,
    read_clipboard_text,
)


def _fake_installed(monkeypatch, installed: set[str]) -> None:
    monkeypatch.setattr(
        clipboard.shutil,
        "which",
        lambda program: f"/usr/bin/{program}" if program in installed else None,
    )


def _fake_run(monkeypatch, stdout: str = "", returncode: int = 0, error=None):
    def fake_run(args, **kwargs):
        if error is not None:
            raise error
        return subprocess.CompletedProcess(args, returncode, stdout=stdout, stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)


def test_find_clipboard_tool_prefers_wayland_then_x11(monkeypatch):
    _fake_installed(monkeypatch, {"wl-paste", "xclip"})

    assert find_clipboard_tool({"WAYLAND_DISPLAY": "wayland-1", "DISPLAY": ":0"}) == (
        WL_PASTE
    )
    assert find_clipboard_tool({"DISPLAY": ":0"}) == XCLIP


def test_find_clipboard_tool_returns_none_when_not_installed(monkeypatch):
    _fake_installed(monkeypatch, set())

    assert (
        find_clipboard_tool({"WAYLAND_DISPLAY": "wayland-1", "DISPLAY": ":0"}) is None
    )


def test_find_clipboard_tool_returns_none_without_display(monkeypatch):
    _fake_installed(monkeypatch, {"wl-paste", "xclip"})

    assert find_clipboard_tool({}) is None


def test_clipboard_has_image_detects_image_mime_type(monkeypatch):
    _fake_run(monkeypatch, stdout="text/plain\nimage/png\n")

    assert clipboard_has_image(WL_PASTE) is True


def test_clipboard_has_image_is_false_for_text(monkeypatch):
    _fake_run(monkeypatch, stdout="text/plain\nUTF8_STRING\n")

    assert clipboard_has_image(XCLIP) is False


def test_clipboard_has_image_is_false_when_tool_fails(monkeypatch):
    _fake_run(monkeypatch, stdout="image/png\n", returncode=1)

    assert clipboard_has_image(WL_PASTE) is False


def test_clipboard_has_image_is_false_on_timeout(monkeypatch):
    _fake_run(monkeypatch, error=subprocess.TimeoutExpired(cmd="wl-paste", timeout=2))

    assert clipboard_has_image(WL_PASTE) is False


def test_read_clipboard_text_returns_text(monkeypatch):
    _fake_run(monkeypatch, stdout="hello")

    assert read_clipboard_text(WL_PASTE) == "hello"


def test_read_clipboard_text_returns_none_on_failure(monkeypatch):
    _fake_run(monkeypatch, error=OSError("no display"))

    assert read_clipboard_text(XCLIP) is None
