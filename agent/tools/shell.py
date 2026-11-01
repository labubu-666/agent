import subprocess
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from .base import Tool

MAX_OUTPUT_CHARS = 20_000


def _truncate(text: str, limit: int = MAX_OUTPUT_CHARS) -> str:
    """Keeps the start and end of long output, dropping the middle."""
    if len(text) <= limit:
        return text
    half = limit // 2
    omitted = len(text) - 2 * half
    return f"{text[:half]}\n...[truncated {omitted} chars]...\n{text[-half:]}"


class RunCommandTool(Tool):
    """A tool to run shell commands and return their output."""

    name = "run_command"
    description = (
        "Runs a shell command and returns its exit code, stdout and stderr. "
        "Useful for running scripts, tests, git, package managers, etc."
    )

    class Args(BaseModel):
        command: str = Field(..., description="The shell command to run.")
        cwd: str = Field(
            default=".",
            description="The working directory to run the command in. Defaults to current directory.",
        )
        timeout: int = Field(
            default=60,
            description="Maximum number of seconds to let the command run. Defaults to 60.",
        )

    args_schema = Args

    def run(self, **kwargs: Any) -> str:
        command = kwargs.get("command", "")
        cwd = kwargs.get("cwd", ".")
        timeout = kwargs.get("timeout", 60)
        if not command:
            return "Error: command is required."

        cwd_path = Path(cwd)
        if not cwd_path.exists():
            return f"Error: Directory '{cwd}' does not exist."
        if not cwd_path.is_dir():
            return f"Error: Path '{cwd}' is not a directory."

        try:
            result = subprocess.run(
                command,
                check=False,
                shell=True,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return (
                f"Exit code: {result.returncode}\n\n"
                f"STDOUT:\n{_truncate(result.stdout)}\n\n"
                f"STDERR:\n{_truncate(result.stderr)}"
            )
        except subprocess.TimeoutExpired:
            return f"Error: Command '{command}' timed out after {timeout} seconds."
        except (OSError, ValueError, subprocess.SubprocessError) as e:
            return f"Error running command '{command}': {e}"
