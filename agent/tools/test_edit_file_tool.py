from pathlib import Path

import pytest

from agent.tools.files import EditFileTool


@pytest.fixture
def tool() -> EditFileTool:
    return EditFileTool()


@pytest.fixture
def test_file(tmp_path) -> Path:
    return tmp_path / "test_file.txt"


def test_edit_existing_file(tool, test_file):
    test_file.write_text("Original content\nLine 2\nLine 3", encoding="utf-8")

    new_content = "New content\nEdited line 2"
    result = tool.run(file_path=str(test_file), content=new_content)

    assert "Successfully edited file" in result
    assert test_file.read_text(encoding="utf-8") == new_content
    assert list(test_file.parent.iterdir()) == [test_file]


def test_edit_nonexistent_file(tool, tmp_path):
    result = tool.run(
        file_path=str(tmp_path / "nonexistent.txt"), content="Some content"
    )

    assert "Error: File" in result
    assert "does not exist" in result


def test_edit_directory_path(tool, tmp_path):
    dir_path = tmp_path / "test_dir"
    dir_path.mkdir()

    result = tool.run(file_path=str(dir_path), content="Some content")

    assert "Error: Path" in result
    assert "is not a file" in result


def test_missing_file_path(tool):
    result = tool.run(file_path="", content="Some content")

    assert "Error: file_path is required" in result


def test_empty_content(tool, test_file):
    test_file.write_text("Some initial content", encoding="utf-8")

    result = tool.run(file_path=str(test_file), content="")

    assert "Successfully edited file" in result
    assert test_file.read_text(encoding="utf-8") == ""


def test_large_content(tool, test_file):
    test_file.write_text("Small initial content", encoding="utf-8")
    large_content = "A" * 10000 + "\n" + "B" * 5000

    result = tool.run(file_path=str(test_file), content=large_content)

    assert f"to {len(large_content.encode('utf-8'))} bytes" in result
    assert test_file.read_text(encoding="utf-8") == large_content


def test_unicode_content(tool, test_file):
    test_file.write_text("ASCII content", encoding="utf-8")
    unicode_content = "Unicode content: 🚀 中文 العربية"

    result = tool.run(file_path=str(test_file), content=unicode_content)

    assert "Successfully edited file" in result
    assert test_file.read_text(encoding="utf-8") == unicode_content


def test_permission_error(tool, test_file, monkeypatch):
    test_file.write_text("test", encoding="utf-8")

    def deny(self, *args, **kwargs):
        raise PermissionError("Permission denied")

    monkeypatch.setattr(Path, "write_text", deny)
    result = tool.run(file_path=str(test_file), content="New content")

    assert "Error: Permission denied when editing file" in result


def test_tool_schema_validation(tool):
    assert tool.name == "edit_file"
    assert tool.description is not None

    fields = tool.args_schema.model_fields
    assert set(fields) == {"file_path", "content"}


def test_size_reporting(tool, test_file):
    test_file.write_text("Hello World", encoding="utf-8")

    result = tool.run(file_path=str(test_file), content="Hi")

    assert "Changed from 11 to 2 bytes" in result
