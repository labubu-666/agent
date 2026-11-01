from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from .base import Tool


class ListFilesTool(Tool):
    """A tool to list files in a directory."""

    name = "list_files_in_directory"
    description = "Lists all files and directories in the specified directory path."

    class Args(BaseModel):
        directory: str = Field(
            default=".",
            description="The directory path to list files from. Defaults to current directory.",
        )

    args_schema = Args

    def run(self, **kwargs: Any) -> str:
        directory = kwargs.get("directory", ".")
        path = Path(directory)
        try:
            if not path.exists():
                return f"Error: Directory '{directory}' does not exist."
            if not path.is_dir():
                return f"Error: Path '{directory}' is not a directory."

            directories: list[str] = []
            files: list[str] = []
            for item in sorted(path.iterdir(), key=lambda p: p.name):
                if item.is_dir():
                    directories.append(f"[DIR] {item.name}")
                else:
                    try:
                        files.append(f"{item.name} ({item.stat().st_size} bytes)")
                    except OSError:
                        files.append(f"{item.name} (size unknown)")

            if not directories and not files:
                return f"Directory '{directory}' is empty."

            result: list[str] = []
            if directories:
                result.append("Directories:")
                result.extend(directories)
            if files:
                if directories:
                    result.append("")
                result.append("Files:")
                result.extend(files)
            return "\n".join(result)
        except PermissionError:
            return f"Error: Permission denied accessing directory '{directory}'."
        except Exception as e:
            return f"Error listing files in directory '{directory}': {e}"


class ReadFileTool(Tool):
    """A tool to read the contents of an existing file."""

    name = "read_file"
    description = "Reads and returns the contents of an existing file."

    class Args(BaseModel):
        file_path: str = Field(description="The path to the file to read.")
        encoding: str = Field(
            default="utf-8",
            description="The encoding to use when reading the file. Defaults to 'utf-8'.",
        )

    args_schema = Args

    def run(self, **kwargs: Any) -> str:
        file_path = kwargs.get("file_path", "")
        encoding = kwargs.get("encoding", "utf-8")
        if not file_path:
            return "Error: file_path is required."

        path = Path(file_path)
        try:
            if not path.exists():
                return f"Error: File '{file_path}' does not exist."
            if not path.is_file():
                return f"Error: Path '{file_path}' is not a file."

            content = path.read_text(encoding=encoding)
            return f"File: {file_path}\nSize: {path.stat().st_size} bytes\nContent:\n{content}"
        except UnicodeDecodeError as e:
            return f"Error: Cannot decode file '{file_path}' with encoding '{encoding}': {e}"
        except PermissionError:
            return f"Error: Permission denied when reading file '{file_path}'."
        except Exception as e:
            return f"Error reading file '{file_path}': {e}"


class CreateFileTool(Tool):
    """A tool to create a new file with specified content."""

    name = "create_new_file"
    description = "Creates a new file at the specified path with the given content."

    class Args(BaseModel):
        file_path: str = Field(
            description="The path where the new file should be created (including filename)."
        )
        content: str = Field(
            default="",
            description="The content to write to the file. Defaults to empty string.",
        )
        overwrite: bool = Field(
            default=False,
            description="Whether to overwrite the file if it already exists. Defaults to False.",
        )

    args_schema = Args

    def run(self, **kwargs: Any) -> str:
        file_path = kwargs.get("file_path", "")
        content = kwargs.get("content", "")
        overwrite = kwargs.get("overwrite", False)
        if not file_path:
            return "Error: file_path is required."

        path = Path(file_path)
        try:
            if path.exists() and not overwrite:
                return f"Error: File '{file_path}' already exists. Use overwrite=True to replace it."

            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            return f"Successfully created file '{file_path}' with {len(content)} characters."
        except PermissionError:
            return f"Error: Permission denied when creating file '{file_path}'."
        except Exception as e:
            return f"Error creating file '{file_path}': {e}"


class EditFileTool(Tool):
    """A tool to replace the entire content of an existing file."""

    name = "edit_file"
    description = (
        "Replaces the entire content of an existing file with the given content."
    )

    class Args(BaseModel):
        file_path: str = Field(description="The path to the file to edit.")
        content: str = Field(
            description="The new content to replace the entire file with."
        )

    args_schema = Args

    def run(self, **kwargs: Any) -> str:
        file_path = kwargs.get("file_path", "")
        content = kwargs.get("content", "")

        if not file_path:
            return "Error: file_path is required."

        path = Path(file_path)
        try:
            if not path.exists():
                return f"Error: File '{file_path}' does not exist."
            if not path.is_file():
                return f"Error: Path '{file_path}' is not a file."

            original_size = len(path.read_bytes())
            path.write_text(content, encoding="utf-8")
            new_size = len(content.encode("utf-8"))
            return f"Successfully edited file '{file_path}'. Changed from {original_size} to {new_size} bytes."
        except PermissionError:
            return f"Error: Permission denied when editing file '{file_path}'."
        except Exception as e:
            return f"Error editing file '{file_path}': {e}"
