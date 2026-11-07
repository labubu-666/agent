import base64
import mimetypes
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from .base import Tool, ToolOutput

MAX_IMAGE_BYTES = 8 * 1024 * 1024


class ImageLoadError(Exception):
    """Raised when an image file cannot be loaded for sending to the model."""


def load_image_data_uri(path: Path, max_bytes: int = MAX_IMAGE_BYTES) -> str:
    """Reads an image file and returns it as a base64 data URI.

    Raises ImageLoadError if the file is missing, is not an image, or exceeds max_bytes.
    """
    if not path.exists():
        raise ImageLoadError(f"File '{path}' does not exist.")
    if not path.is_file():
        raise ImageLoadError(f"Path '{path}' is not a file.")

    mime_type, _ = mimetypes.guess_type(path.name)
    if mime_type is None or not mime_type.startswith("image/"):
        raise ImageLoadError(f"File '{path}' is not a recognized image type.")

    size = path.stat().st_size
    if size > max_bytes:
        raise ImageLoadError(
            f"File '{path}' is {size} bytes, which exceeds the maximum of {max_bytes} bytes."
        )

    try:
        data = path.read_bytes()
    except PermissionError as e:
        raise ImageLoadError(f"Permission denied when reading file '{path}'.") from e
    encoded = base64.b64encode(data).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


class ReadImageTool(Tool):
    """A tool that attaches an image file so the model can see it."""

    name = "read_image"
    description = (
        "Loads an image file (png, jpg, gif, webp, etc.) so you can see it. "
        "The image is attached to the next message."
    )

    class Args(BaseModel):
        file_path: str = Field(description="The path to the image file to load.")
        max_bytes: int = Field(
            default=MAX_IMAGE_BYTES,
            description=f"Maximum image size in bytes. Defaults to {MAX_IMAGE_BYTES} (8 MB).",
        )

    args_schema = Args

    def run(self, **kwargs: Any) -> str:
        return self.execute(**kwargs).text

    def execute(self, **kwargs: Any) -> ToolOutput:
        file_path = kwargs.get("file_path", "")
        max_bytes = kwargs.get("max_bytes", MAX_IMAGE_BYTES)
        if not file_path:
            return ToolOutput(text="Error: file_path is required.")

        path = Path(file_path)
        try:
            load_image_data_uri(path, max_bytes=max_bytes)
        except ImageLoadError as e:
            return ToolOutput(text=f"Error: {e}")
        except OSError as e:
            return ToolOutput(text=f"Error reading image '{file_path}': {e}")

        mime_type = mimetypes.guess_type(path.name)[0]
        size = path.stat().st_size
        return ToolOutput(
            text=f"Attached image '{file_path}' ({mime_type}, {size} bytes).",
            image_paths=[str(path.resolve())],
        )
