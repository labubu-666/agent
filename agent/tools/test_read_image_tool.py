import base64
from pathlib import Path

import pytest

from agent.tools import TOOL_REGISTRY
from agent.tools.image import (
    MAX_IMAGE_BYTES,
    ImageLoadError,
    ReadImageTool,
    load_image_data_uri,
)

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
JPEG_BYTES = b"\xff\xd8\xff\xe0" + b"\x01" * 32


@pytest.fixture
def tool() -> ReadImageTool:
    return ReadImageTool()


def test_png_is_attached_as_data_uri(tool, tmp_path):
    image = tmp_path / "pic.png"
    image.write_bytes(PNG_BYTES)

    output = tool.execute(file_path=str(image), max_bytes=MAX_IMAGE_BYTES)

    assert output.image_paths == [str(image.resolve())]
    assert "image/png" in output.text
    assert f"{len(PNG_BYTES)} bytes" in output.text


def test_loader_returns_decodable_data_uri(tmp_path):
    image = tmp_path / "pic.png"
    image.write_bytes(PNG_BYTES)

    uri = load_image_data_uri(image)

    prefix = "data:image/png;base64,"
    assert uri.startswith(prefix)
    assert base64.b64decode(uri[len(prefix) :]) == PNG_BYTES


def test_jpeg_mime_type_is_detected(tmp_path):
    image = tmp_path / "photo.jpg"
    image.write_bytes(JPEG_BYTES)

    assert load_image_data_uri(image).startswith("data:image/jpeg;base64,")


def test_run_returns_text_only(tool, tmp_path):
    image = tmp_path / "pic.png"
    image.write_bytes(PNG_BYTES)

    result = tool.run(file_path=str(image))

    assert result.startswith("Attached image")
    assert "data:" not in result


def test_missing_file_path(tool):
    output = tool.execute(file_path="")

    assert output.text == "Error: file_path is required."
    assert output.image_paths == []


def test_nonexistent_file(tool, tmp_path):
    output = tool.execute(file_path=str(tmp_path / "missing.png"))

    assert output.text.startswith("Error: File")
    assert "does not exist" in output.text
    assert output.image_paths == []


def test_directory_path(tool, tmp_path):
    folder = tmp_path / "images.png"
    folder.mkdir()

    output = tool.execute(file_path=str(folder))

    assert "is not a file" in output.text
    assert output.image_paths == []


def test_non_image_file_is_rejected(tool, tmp_path):
    text_file = tmp_path / "notes.txt"
    text_file.write_text("hello", encoding="utf-8")

    output = tool.execute(file_path=str(text_file))

    assert "is not a recognized image type" in output.text
    assert output.image_paths == []


def test_file_over_max_bytes_is_rejected(tool, tmp_path):
    image = tmp_path / "big.png"
    image.write_bytes(PNG_BYTES)

    output = tool.execute(file_path=str(image), max_bytes=10)

    assert "exceeds the maximum of 10 bytes" in output.text
    assert output.image_paths == []


def test_file_exactly_at_limit_is_accepted(tmp_path):
    image = tmp_path / "exact.png"
    image.write_bytes(PNG_BYTES)

    assert load_image_data_uri(image, max_bytes=len(PNG_BYTES)).startswith(
        "data:image/png;base64,"
    )


def test_default_max_bytes_is_eight_megabytes(tool):
    assert MAX_IMAGE_BYTES == 8 * 1024 * 1024
    assert tool.args_schema(file_path="x.png").max_bytes == 8 * 1024 * 1024


def test_loader_raises_on_oversized_file(tmp_path):
    image = tmp_path / "big.png"
    image.write_bytes(PNG_BYTES)

    with pytest.raises(ImageLoadError, match="exceeds the maximum"):
        load_image_data_uri(image, max_bytes=1)


def test_permission_error(tool, tmp_path, monkeypatch):
    image = tmp_path / "locked.png"
    image.write_bytes(PNG_BYTES)

    def deny(self, *args, **kwargs):
        raise PermissionError("Permission denied")

    monkeypatch.setattr(Path, "read_bytes", deny)
    output = tool.execute(file_path=str(image))

    assert "Permission denied when reading file" in output.text
    assert output.image_paths == []


def test_tool_is_registered_with_expected_schema():
    tool = TOOL_REGISTRY["read_image"]

    assert isinstance(tool, ReadImageTool)
    assert set(tool.args_schema.model_fields) == {"file_path", "max_bytes"}
