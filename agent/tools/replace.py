from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from .base import Tool


class ReplaceTextInFileTool(Tool):
    """A tool to replace a specific line in a file."""

    name = "replace_text_in_file"
    description = "Replaces a specific line in a file with new text."

    class Args(BaseModel):
        file_path: str = Field(..., description="The path to the file.")
        line_number: int = Field(..., description="The line number to replace.")
        new_text: str = Field(..., description="The new text for the line.")

    args_schema = Args

    def run(self, **kwargs: Any) -> str:
        file_path = kwargs["file_path"]
        line_number = kwargs["line_number"]
        new_text = kwargs["new_text"]
        path = Path(file_path)
        try:
            lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
            if line_number > len(lines) or line_number < 1:
                return f"Error: Line number {line_number} is out of range."

            lines[line_number - 1] = new_text + "\n"
            path.write_text("".join(lines), encoding="utf-8")
            return f"Successfully replaced line {line_number} in {file_path}."
        except (OSError, UnicodeError) as e:
            return f"Error replacing text in file: {e}"
