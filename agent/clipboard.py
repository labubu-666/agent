"""Reads the system clipboard through the OS clipboard tool for the current session."""

import os
import shutil
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass

CLIPBOARD_TIMEOUT_SECONDS = 2


@dataclass(frozen=True)
class ClipboardTool:
    """A command-line clipboard tool and the commands used to query it."""

    program: str
    list_types_args: tuple[str, ...]
    read_text_args: tuple[str, ...]


WL_PASTE = ClipboardTool(
    program="wl-paste",
    list_types_args=("wl-paste", "--list-types"),
    read_text_args=("wl-paste", "--no-newline"),
)
XCLIP = ClipboardTool(
    program="xclip",
    list_types_args=("xclip", "-selection", "clipboard", "-t", "TARGETS", "-o"),
    read_text_args=("xclip", "-selection", "clipboard", "-o"),
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


def clipboard_has_image(tool: ClipboardTool) -> bool:
    """Returns True if the clipboard currently holds an image. Failures count as no."""
    try:
        result = subprocess.run(
            list(tool.list_types_args),
            check=False,
            capture_output=True,
            text=True,
            timeout=CLIPBOARD_TIMEOUT_SECONDS,
        )
    except OSError, subprocess.SubprocessError:
        return False
    if result.returncode != 0:
        return False
    return any(line.strip().startswith("image/") for line in result.stdout.splitlines())


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
