from pathlib import Path

import pytest

from agent.tools.replace import ReplaceTextInFileTool


@pytest.fixture
def tool() -> ReplaceTextInFileTool:
    return ReplaceTextInFileTool()


def test_replace_line(tool, tmp_path):
    test_file = tmp_path / "test.txt"
    test_file.write_text("one\ntwo\nthree\n", encoding="utf-8")

    result = tool.run(file_path=str(test_file), line_number=2, new_text="TWO")

    assert "Successfully replaced line 2" in result
    assert test_file.read_text(encoding="utf-8") == "one\nTWO\nthree\n"


def test_line_out_of_range(tool, tmp_path):
    test_file = tmp_path / "test.txt"
    test_file.write_text("one\n", encoding="utf-8")

    result = tool.run(file_path=str(test_file), line_number=5, new_text="x")

    assert "out of range" in result


def test_missing_file_is_reported(tool, tmp_path):
    result = tool.run(
        file_path=str(tmp_path / "missing.txt"), line_number=1, new_text="x"
    )

    assert "Error replacing text in file" in result


def test_os_error_is_reported(tool, tmp_path, monkeypatch):
    test_file = tmp_path / "test.txt"
    test_file.write_text("one\n", encoding="utf-8")

    def fail(self, *args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(Path, "write_text", fail)
    result = tool.run(file_path=str(test_file), line_number=1, new_text="x")

    assert "Error replacing text in file" in result
    assert "disk full" in result


def test_undecodable_file_is_reported(tool, tmp_path):
    test_file = tmp_path / "binary.bin"
    test_file.write_bytes(b"\xff\xfe\x00bad")

    result = tool.run(file_path=str(test_file), line_number=1, new_text="x")

    assert "Error replacing text in file" in result
