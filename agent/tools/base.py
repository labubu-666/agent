from typing import Any

from pydantic import BaseModel, Field


class ToolOutput(BaseModel):
    """The result of a tool run: text for the model, plus optional image files to attach."""

    text: str = Field(..., description="The text observation returned to the model.")
    image_paths: list[str] = Field(
        default_factory=list,
        description="Absolute paths of image files to attach to the next message.",
    )


class Tool:
    """Base class for all tools. Subclasses set `name`, `description` and `args_schema`."""

    name: str
    description: str
    args_schema: type[BaseModel]

    def run(self, **kwargs: Any) -> str:
        raise NotImplementedError

    def execute(self, **kwargs: Any) -> ToolOutput:
        """Runs the tool and returns its output. Override when the tool attaches images."""
        return ToolOutput(text=self.run(**kwargs))
