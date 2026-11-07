import subprocess

from agent import clipboard
from agent.clipboard import (
    WL_PASTE,
    XCLIP,
    clipboard_image_files,
    clipboard_image_type,
    find_clipboard_tool,
    read_clipboard_bytes,
    read_clipboard_text,
    save_clipboard_image,
)


def _fake_installed(monkeypatch, installed: set[str]) -> None:
    monkeypatch.setattr(
        clipboard.shutil,
        "which",
        lambda program: f"/usr/bin/{program}" if program in installed else None,
    )


def _fake_run(monkeypatch, stdout: bytes | str = b"", returncode: int = 0, error=None):
    def fake_run(args, **kwargs):
        if error is not None:
            raise error
        return subprocess.CompletedProcess(args, returncode, stdout=stdout, stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)


def _fake_run_by_args(monkeypatch, responses: dict[str, bytes]) -> list[list[str]]:
    """Answers each clipboard command by its MIME type argument and records the calls."""
    calls: list[list[str]] = []

    def fake_run(args, **kwargs):
        calls.append(list(args))
        key = next((arg for arg in args if arg in responses), "list")
        stdout = responses.get(key, b"")
        if kwargs.get("text"):
            stdout = stdout.decode("utf-8")
        return subprocess.CompletedProcess(args, 0, stdout=stdout, stderr=None)

    monkeypatch.setattr(subprocess, "run", fake_run)
    return calls


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


def test_clipboard_image_type_prefers_png(monkeypatch):
    _fake_run(monkeypatch, stdout="text/plain\nimage/jpeg\nimage/png\n")

    assert clipboard_image_type(WL_PASTE) == "image/png"


def test_clipboard_image_type_returns_first_other_image_type(monkeypatch):
    _fake_run(monkeypatch, stdout="text/plain\nimage/jpeg\n")

    assert clipboard_image_type(WL_PASTE) == "image/jpeg"


def test_clipboard_image_type_is_none_for_text(monkeypatch):
    _fake_run(monkeypatch, stdout="text/plain\nUTF8_STRING\n")

    assert clipboard_image_type(XCLIP) is None


def test_clipboard_image_type_is_none_when_tool_fails(monkeypatch):
    _fake_run(monkeypatch, stdout="image/png\n", returncode=1)

    assert clipboard_image_type(WL_PASTE) is None


def test_clipboard_image_type_is_none_on_timeout(monkeypatch):
    _fake_run(monkeypatch, error=subprocess.TimeoutExpired(cmd="wl-paste", timeout=2))

    assert clipboard_image_type(WL_PASTE) is None


def test_read_clipboard_bytes_requests_the_mime_type(monkeypatch):
    calls = _fake_run_by_args(monkeypatch, {"image/png": b"\x89PNG"})

    assert read_clipboard_bytes(WL_PASTE, "image/png") == b"\x89PNG"
    assert calls == [["wl-paste", "--no-newline", "--type", "image/png"]]


def test_read_clipboard_bytes_uses_xclip_target(monkeypatch):
    calls = _fake_run_by_args(monkeypatch, {"image/png": b"\x89PNG"})

    assert read_clipboard_bytes(XCLIP, "image/png") == b"\x89PNG"
    assert calls == [["xclip", "-selection", "clipboard", "-t", "image/png", "-o"]]


def test_read_clipboard_bytes_returns_none_on_failure(monkeypatch):
    _fake_run(monkeypatch, returncode=1, stdout=b"\x89PNG")

    assert read_clipboard_bytes(WL_PASTE, "image/png") is None


def test_read_clipboard_bytes_returns_none_when_empty(monkeypatch):
    _fake_run(monkeypatch, stdout=b"")

    assert read_clipboard_bytes(WL_PASTE, "image/png") is None


def test_read_clipboard_bytes_returns_none_on_timeout(monkeypatch):
    _fake_run(monkeypatch, error=subprocess.TimeoutExpired(cmd="wl-paste", timeout=2))

    assert read_clipboard_bytes(WL_PASTE, "image/png") is None


def test_clipboard_image_files_returns_copied_image_file(tmp_path, monkeypatch):
    image = tmp_path / "shot.png"
    image.write_bytes(b"\x89PNG")
    uri = f"file://{image}\n".encode()
    _fake_run_by_args(monkeypatch, {"text/uri-list": uri, "list": b"text/uri-list\n"})

    assert clipboard_image_files(WL_PASTE) == [image.resolve()]


def test_clipboard_image_files_ignores_non_image_files(tmp_path, monkeypatch):
    document = tmp_path / "notes.txt"
    document.write_text("hi", encoding="utf-8")
    uri = f"file://{document}\n".encode()
    _fake_run_by_args(monkeypatch, {"text/uri-list": uri, "list": b"text/uri-list\n"})

    assert clipboard_image_files(WL_PASTE) == []


def test_clipboard_image_files_is_empty_without_uri_list(monkeypatch):
    _fake_run(monkeypatch, stdout="text/plain\n")

    assert clipboard_image_files(WL_PASTE) == []


def test_save_clipboard_image_writes_unique_png(tmp_path):
    first = save_clipboard_image(b"one", "image/png", tmp_path / "attachments")
    second = save_clipboard_image(b"two", "image/png", tmp_path / "attachments")

    assert first.suffix == ".png"
    assert first != second
    assert first.read_bytes() == b"one"
    assert second.read_bytes() == b"two"
    assert first.parent == (tmp_path / "attachments").resolve()


def test_read_clipboard_text_returns_text(monkeypatch):
    _fake_run(monkeypatch, stdout="hello")

    assert read_clipboard_text(WL_PASTE) == "hello"


def test_read_clipboard_text_returns_none_on_failure(monkeypatch):
    _fake_run(monkeypatch, error=OSError("no display"))

    assert read_clipboard_text(XCLIP) is None
