from typing import Any

from pydantic import BaseModel, Field

from .base import Tool


class PrintToConsoleTool(Tool):
    """A tool to print messages to the console for debugging or output."""

    name = "print_to_console"
    description = "Prints a given message to the console. Useful for debugging or showing intermediate results."

    class Args(BaseModel):
        message: str = Field(..., description="The message to print to the console.")

    args_schema = Args

    def run(self, **kwargs: Any) -> str:
        message = kwargs["message"]
        print(message)
        return f"Message printed: {message}"
