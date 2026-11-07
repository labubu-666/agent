"""Loads project instruction files (AGENTS.md and CLAUDE.md) for the agent.

Startup files are the global ones plus every instruction file from the git root (or the
filesystem root when there is no repo) down to the working directory. Files in subfolders
below the working directory are loaded the first time a tool touches that folder.
"""

from collections.abc import Iterable
from itertools import islice
from pathlib import Path

import structlog

logger = structlog.get_logger(__name__)

INSTRUCTION_FILE_NAMES = ("AGENTS.md", "CLAUDE.md")
MAX_LINES = 1000
# Tool arguments that may name a file or folder the agent is about to work in.
PATH_ARGUMENT_NAMES = ("file_path", "directory")


def _global_instruction_files(home: Path) -> list[Path]:
    return [home / ".config" / "agent" / "AGENTS.md", home / ".claude" / "CLAUDE.md"]


def _folders_from_root_to(cwd: Path) -> list[Path]:
    """Returns the folders from the git root (or the filesystem root) down to cwd."""
    ancestors = [cwd, *cwd.parents]
    root = next((f for f in ancestors if (f / ".git").exists()), ancestors[-1])
    return list(reversed(ancestors[: ancestors.index(root) + 1]))


def _files_in(folder: Path) -> list[Path]:
    return [
        folder / name for name in INSTRUCTION_FILE_NAMES if (folder / name).is_file()
    ]


def _unique(paths: Iterable[Path]) -> list[Path]:
    """Drops paths that resolve to a file already in the list (e.g. a symlinked CLAUDE.md)."""
    seen: set[Path] = set()
    result: list[Path] = []
    for path in paths:
        resolved = path.resolve()
        if resolved not in seen:
            seen.add(resolved)
            result.append(path)
    return result


def find_startup_files(cwd: Path, home: Path) -> list[Path]:
    """Returns the global files first, then each folder from the root down to cwd."""
    cwd = cwd.resolve()
    folder_files = (
        f for folder in _folders_from_root_to(cwd) for f in _files_in(folder)
    )
    candidates = [*_global_instruction_files(home), *folder_files]
    return _unique(p for p in candidates if p.is_file())


def find_subdirectory_files(cwd: Path, target: Path) -> list[Path]:
    """Returns instruction files in folders strictly below cwd that lead to target."""
    cwd = cwd.resolve()
    target = target.resolve()
    folder = target if target.is_dir() else target.parent
    if folder == cwd or not folder.is_relative_to(cwd):
        return []
    parts = folder.relative_to(cwd).parts
    subfolders = [cwd.joinpath(*parts[:i]) for i in range(1, len(parts) + 1)]
    return _unique(f for sub in subfolders for f in _files_in(sub))


def read_instruction_file(path: Path) -> str | None:
    """Returns the file's text, cut to MAX_LINES, or None if it cannot be read."""
    try:
        with path.open(encoding="utf-8") as f:
            lines = list(islice(f, MAX_LINES + 1))
    except (OSError, UnicodeError) as e:
        logger.warning("Cannot read instruction file", path=str(path), error=str(e))
        return None

    content = "".join(lines[:MAX_LINES])
    if len(lines) > MAX_LINES:
        content += f"\n[truncated: {path} exceeds {MAX_LINES} lines]\n"
    return content


def load_startup_instructions(cwd: Path, home: Path) -> tuple[str | None, set[Path]]:
    """Returns the startup instruction text (or None) and the resolved paths it loaded."""
    blocks: list[str] = []
    loaded: set[Path] = set()
    for path in find_startup_files(cwd, home):
        content = read_instruction_file(path)
        loaded.add(path.resolve())
        if content is not None:
            blocks.append(f"Instructions from {path}:\n{content}")
    return ("\n\n".join(blocks) or None), loaded


def load_subdirectory_instructions(cwd: Path, target: Path, loaded: set[Path]) -> str:
    """Returns instruction text for folders below cwd that are not yet in `loaded`.

    `loaded` is updated with every file read, so each file is returned at most once.
    """
    blocks: list[str] = []
    for path in find_subdirectory_files(cwd, target):
        resolved = path.resolve()
        if resolved in loaded:
            continue
        loaded.add(resolved)
        content = read_instruction_file(path)
        if content is not None:
            blocks.append(
                f"[Instructions for {path.parent}/ (from {path}) "
                f"- apply only to files under this directory]\n{content}"
            )
    return "\n\n".join(blocks)
