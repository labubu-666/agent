"""Reads the system clipboard through the OS clipboard tool for the current session."""

import mimetypes
import os
import shutil
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlparse

from .session import uuid7

CLIPBOARD_TIMEOUT_SECONDS = 2
PREFERRED_IMAGE_TYPE = "image/png"
URI_LIST_TYPE = "text/uri-list"


@dataclass(frozen=True)
class ClipboardTool:
    """A command-line clipboard tool and the commands used to query it.

    read_type_args contains a '{mime}' placeholder for the MIME type to read.
    """

    program: str
    list_types_args: tuple[str, ...]
    read_text_args: tuple[str, ...]
    read_type_args: tuple[str, ...]

    def read_args(self, mime_type: str) -> list[str]:
        """Returns the command that reads the clipboard content of one MIME type."""
        return [arg.replace("{mime}", mime_type) for arg in self.read_type_args]


WL_PASTE = ClipboardTool(
    program="wl-paste",
    list_types_args=("wl-paste", "--list-types"),
    read_text_args=("wl-paste", "--no-newline"),
    read_type_args=("wl-paste", "--no-newline", "--type", "{mime}"),
)
XCLIP = ClipboardTool(
    program="xclip",
    list_types_args=("xclip", "-selection", "clipboard", "-t", "TARGETS", "-o"),
    read_text_args=("xclip", "-selection", "clipboard", "-o"),
    read_type_args=("xclip", "-selection", "clipboard", "-t", "{mime}", "-o"),
)


def find_clipboard_tool(
    environ: Mapping[str, str] = os.environ,
) -> ClipboardTool | None:
    """Returns the clipboard tool for the current display server, if installed."""
    candidates: list[ClipboardTool] = []
    if environ.get("WAYLAND_DISPLAY"):
        candidates.append(WL_PASTE)
    if environ.get("DISPLAY"):
        candidates.append(XCLIP)
    for tool in candidates:
        if shutil.which(tool.program) is not None:
            return tool
    return None


def _clipboard_types(tool: ClipboardTool) -> list[str]:
    """Returns the MIME types currently on the clipboard. Failures return an empty list."""
    try:
        result = subprocess.run(
            list(tool.list_types_args),
            check=False,
            capture_output=True,
            text=True,
            timeout=CLIPBOARD_TIMEOUT_SECONDS,
        )
    except OSError, subprocess.SubprocessError:
        return []
    if result.returncode != 0:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def clipboard_image_type(tool: ClipboardTool) -> str | None:
    """Returns the image MIME type on the clipboard, preferring PNG. None if there is none."""
    image_types = [t for t in _clipboard_types(tool) if t.startswith("image/")]
    if not image_types:
        return None
    if PREFERRED_IMAGE_TYPE in image_types:
        return PREFERRED_IMAGE_TYPE
    return image_types[0]


def read_clipboard_bytes(tool: ClipboardTool, mime_type: str) -> bytes | None:
    """Returns the clipboard content of one MIME type, or None if it cannot be read."""
    try:
        result = subprocess.run(
            tool.read_args(mime_type),
            check=False,
            capture_output=True,
            timeout=CLIPBOARD_TIMEOUT_SECONDS,
        )
    except OSError, subprocess.SubprocessError:
        return None
    if result.returncode != 0 or not result.stdout:
        return None
    return result.stdout


def clipboard_image_files(tool: ClipboardTool) -> list[Path]:
    """Returns existing image files copied as file references, e.g. from a file manager."""
    if URI_LIST_TYPE not in _clipboard_types(tool):
        return []
    data = read_clipboard_bytes(tool, URI_LIST_TYPE)
    if data is None:
        return []
    paths: list[Path] = []
    for line in data.decode("utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line.startswith("file://"):
            continue
        path = Path(unquote(urlparse(line).path))
        mime_type, _ = mimetypes.guess_type(path.name)
        if mime_type and mime_type.startswith("image/") and path.is_file():
            paths.append(path.resolve())
    return paths


def save_clipboard_image(data: bytes, mime_type: str, directory: Path) -> Path:
    """Saves clipboard image bytes to a new uniquely named file and returns its absolute path."""
    extension = mimetypes.guess_extension(mime_type) or ".bin"
    directory = directory.resolve()
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{uuid7()}{extension}"
    path.write_bytes(data)
    return path


def read_clipboard_text(tool: ClipboardTool) -> str | None:
    """Returns the clipboard text, or None if it cannot be read."""
    try:
        result = subprocess.run(
            list(tool.read_text_args),
            check=False,
            capture_output=True,
            text=True,
            timeout=CLIPBOARD_TIMEOUT_SECONDS,
        )
    except OSError, subprocess.SubprocessError:
        return None
    if result.returncode != 0:
        return None
    return result.stdout
