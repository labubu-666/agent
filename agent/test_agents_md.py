from pathlib import Path

from agent.agents_md import (
    MAX_LINES,
    find_startup_files,
    find_subdirectory_files,
    load_startup_instructions,
    load_subdirectory_instructions,
    read_instruction_file,
)


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    return repo


def test_no_instruction_files_found(tmp_path):
    repo = _repo(tmp_path)
    home = tmp_path / "home"

    assert find_startup_files(repo, home) == []
    assert load_startup_instructions(repo, home) == (None, set())


def test_agents_md_and_claude_md_in_one_folder_both_load_in_order(tmp_path):
    repo = _repo(tmp_path)
    (repo / "AGENTS.md").write_text("agents rules\n")
    (repo / "CLAUDE.md").write_text("claude rules\n")

    files = find_startup_files(repo, tmp_path / "home")

    assert [f.name for f in files] == ["AGENTS.md", "CLAUDE.md"]


def test_symlinked_claude_md_is_loaded_once(tmp_path):
    repo = _repo(tmp_path)
    (repo / "AGENTS.md").write_text("shared rules\n")
    (repo / "CLAUDE.md").symlink_to(repo / "AGENTS.md")

    files = find_startup_files(repo, tmp_path / "home")

    assert [f.name for f in files] == ["AGENTS.md"]


def test_startup_folders_run_from_git_root_to_working_dir(tmp_path):
    repo = _repo(tmp_path)
    nested = repo / "pkg" / "core"
    nested.mkdir(parents=True)
    (repo / "AGENTS.md").write_text("root\n")
    (repo / "pkg" / "AGENTS.md").write_text("pkg\n")
    (nested / "CLAUDE.md").write_text("core\n")

    files = find_startup_files(nested, tmp_path / "home")

    assert files == [
        repo / "AGENTS.md",
        repo / "pkg" / "AGENTS.md",
        nested / "CLAUDE.md",
    ]


def test_search_stops_at_git_root(tmp_path):
    (tmp_path / "AGENTS.md").write_text("outside the repo\n")
    repo = _repo(tmp_path)

    assert find_startup_files(repo, tmp_path / "home") == []


def test_global_files_come_first(tmp_path):
    repo = _repo(tmp_path)
    home = tmp_path / "home"
    (home / ".config" / "agent").mkdir(parents=True)
    (home / ".claude").mkdir(parents=True)
    (home / ".config" / "agent" / "AGENTS.md").write_text("global agent\n")
    (home / ".claude" / "CLAUDE.md").write_text("global claude\n")
    (repo / "AGENTS.md").write_text("project\n")

    files = find_startup_files(repo, home)

    assert files == [
        home / ".config" / "agent" / "AGENTS.md",
        home / ".claude" / "CLAUDE.md",
        repo / "AGENTS.md",
    ]


def test_long_file_is_cut_to_max_lines_with_note(tmp_path):
    path = tmp_path / "AGENTS.md"
    path.write_text("".join(f"line {i}\n" for i in range(MAX_LINES + 50)))

    content = read_instruction_file(path)

    assert content is not None
    assert f"line {MAX_LINES - 1}\n" in content
    assert f"line {MAX_LINES}\n" not in content
    assert f"[truncated: {path} exceeds {MAX_LINES} lines]" in content


def test_unreadable_file_is_skipped(tmp_path):
    path = tmp_path / "AGENTS.md"
    path.write_bytes(b"\xff\xfe not utf-8 \x00")

    assert read_instruction_file(path) is None


def test_startup_text_has_heading_per_file(tmp_path):
    repo = _repo(tmp_path)
    (repo / "AGENTS.md").write_text("project rules\n")

    text, loaded = load_startup_instructions(repo, tmp_path / "home")

    assert text is not None
    assert f"Instructions from {repo / 'AGENTS.md'}:" in text
    assert "project rules" in text
    assert loaded == {(repo / "AGENTS.md").resolve()}


def test_subdirectory_files_are_found_between_cwd_and_target(tmp_path):
    repo = _repo(tmp_path)
    (repo / "src" / "api").mkdir(parents=True)
    (repo / "src" / "AGENTS.md").write_text("src\n")
    (repo / "src" / "api" / "CLAUDE.md").write_text("api\n")
    (repo / "docs").mkdir()
    (repo / "docs" / "AGENTS.md").write_text("docs\n")

    files = find_subdirectory_files(repo, repo / "src" / "api" / "client.py")

    assert files == [repo / "src" / "AGENTS.md", repo / "src" / "api" / "CLAUDE.md"]


def test_subdirectory_files_ignore_working_dir_and_outside_paths(tmp_path):
    repo = _repo(tmp_path)
    (repo / "AGENTS.md").write_text("root\n")
    (repo / "src").mkdir()
    (repo / "src" / "AGENTS.md").write_text("src\n")

    assert find_subdirectory_files(repo, repo / "README.md") == []
    assert find_subdirectory_files(repo, tmp_path / "elsewhere" / "x.py") == []


def test_subdirectory_instructions_are_loaded_once(tmp_path):
    repo = _repo(tmp_path)
    (repo / "src").mkdir()
    (repo / "src" / "AGENTS.md").write_text("src rules\n")
    loaded: set[Path] = set()

    first = load_subdirectory_instructions(repo, repo / "src" / "a.py", loaded)
    second = load_subdirectory_instructions(repo, repo / "src" / "b.py", loaded)

    assert "src rules" in first
    assert "apply only to files under this directory" in first
    assert second == ""
