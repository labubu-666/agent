from pathlib import Path

import pytest

from agent.tools.files import ReadFileTool


@pytest.fixture
def tool() -> ReadFileTool:
    return ReadFileTool()


def test_read_existing_file(tool, tmp_path):
    test_file = tmp_path / "test_file.txt"
    content = "Hello, World!\nThis is a test file.\nLine 3"
    test_file.write_text(content, encoding="utf-8")

    result = tool.run(file_path=str(test_file))

    assert "File:" in result
    assert str(test_file) in result
    assert "Size:" in result
    assert "Content:" in result
    assert content in result


def test_read_empty_file(tool, tmp_path):
    test_file = tmp_path / "empty.txt"
    test_file.write_text("", encoding="utf-8")

    result = tool.run(file_path=str(test_file))

    assert "Size: 0 bytes" in result
    assert "Content:" in result


def test_read_unicode_file(tool, tmp_path):
    test_file = tmp_path / "unicode.txt"
    content = "Unicode test: 🚀 🐍 ñáéíóú 中文 العربية"
    test_file.write_text(content, encoding="utf-8")

    result = tool.run(file_path=str(test_file), encoding="utf-8")

    assert content in result


def test_read_nonexistent_file(tool, tmp_path):
    result = tool.run(file_path=str(tmp_path / "nonexistent.txt"))

    assert "Error: File" in result
    assert "does not exist" in result


def test_read_directory_path(tool, tmp_path):
    dir_path = tmp_path / "test_dir"
    dir_path.mkdir()

    result = tool.run(file_path=str(dir_path))

    assert "Error: Path" in result
    assert "is not a file" in result


def test_missing_file_path(tool):
    result = tool.run(file_path="")

    assert "Error: file_path is required" in result


def test_different_encoding(tool, tmp_path):
    test_file = tmp_path / "latin.txt"
    content = "Test with special chars: áéíóú"
    test_file.write_text(content, encoding="latin-1")

    result = tool.run(file_path=str(test_file), encoding="latin-1")

    assert content in result


def test_wrong_encoding(tool, tmp_path):
    test_file = tmp_path / "unicode.txt"
    test_file.write_text("Unicode: 中文", encoding="utf-8")

    result = tool.run(file_path=str(test_file), encoding="ascii")

    assert "Error: Cannot decode file" in result
    assert "encoding 'ascii'" in result


def test_unknown_encoding_is_reported(tool, tmp_path):
    test_file = tmp_path / "test.txt"
    test_file.write_text("test", encoding="utf-8")

    result = tool.run(file_path=str(test_file), encoding="utf-9")

    assert "Error reading file" in result
    assert "utf-9" in result


def test_large_file(tool, tmp_path):
    test_file = tmp_path / "large.txt"
    content = "A" * 50000 + "\n" + "B" * 50000
    test_file.write_text(content, encoding="utf-8")

    result = tool.run(file_path=str(test_file))

    assert content in result
    assert "Size:" in result


def test_permission_error(tool, tmp_path, monkeypatch):
    test_file = tmp_path / "test.txt"
    test_file.write_text("test", encoding="utf-8")

    def deny(self, *args, **kwargs):
        raise PermissionError("Permission denied")

    monkeypatch.setattr(Path, "read_text", deny)
    result = tool.run(file_path=str(test_file))

    assert "Error: Permission denied when reading file" in result


def test_tool_schema_validation(tool):
    assert tool.name == "read_file"
    assert tool.description is not None

    fields = tool.args_schema.model_fields
    assert "file_path" in fields
    assert "encoding" in fields
    assert tool.args_schema(file_path="test").encoding == "utf-8"


def test_multiline_file(tool, tmp_path):
    test_file = tmp_path / "multi.txt"
    content = """Line 1: Basic text
Line 2: Text with    extra spaces
Line 3: 

Line 5: Text after empty line
Final line without newline"""
    test_file.write_text(content, encoding="utf-8")

    result = tool.run(file_path=str(test_file))

    assert content in result


def test_binary_file_handling(tool, tmp_path):
    test_file = tmp_path / "binary.bin"
    test_file.write_bytes(b"\x00\x01\x02\xff\xfe")

    result = tool.run(file_path=str(test_file))

    assert "File:" in result or "Error:" in result
