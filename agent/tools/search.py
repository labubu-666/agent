import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field
from ripgrepy import Ripgrepy

from .base import Tool


class SearchTextInDirectoryTool(Tool):
    """A tool to search for text in files within a directory."""

    name = "search_text_in_directory"
    description = (
        "Searches for a given text in all files within a specified directory. "
        "Useful for finding occurrences of text in code, logs, or documents."
    )

    class Args(BaseModel):
        directory: str = Field(..., description="The directory path to search in.")
        text: str = Field(..., description="The text to search for in the files.")

    args_schema = Args

    def run(self, **kwargs: Any) -> str:
        directory = kwargs["directory"]
        text = kwargs["text"]
        path = Path(directory)
        if not path.exists():
            return json.dumps({"error": f"Directory '{directory}' does not exist."})
        if not path.is_dir():
            return json.dumps({"error": f"Path '{directory}' is not a directory."})

        rg = Ripgrepy(text, str(path.resolve()))
        result = rg.glob("!.venv,!node_modules").json().run().as_dict
        return json.dumps(result)
