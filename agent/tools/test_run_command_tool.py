import subprocess

from agent.tools import TOOL_REGISTRY
from agent.tools.shell import MAX_OUTPUT_CHARS, RunCommandTool


class TestRunCommandTool:
    """Test cases for the RunCommandTool."""

    def setup_method(self):
        """Set up test fixtures before each test method."""
        self.tool = RunCommandTool()

    def test_successful_command(self):
        """Test running a command that succeeds."""
        result = self.tool.run(command="echo hello")

        assert "Exit code: 0" in result
        assert "STDOUT:\nhello" in result

    def test_failing_command_exit_code(self):
        """Test that a non-zero exit code is reported."""
        result = self.tool.run(command="exit 3")

        assert "Exit code: 3" in result

    def test_stderr_captured(self):
        """Test that stderr is returned."""
        result = self.tool.run(command="echo oops 1>&2")

        assert "STDERR:\noops" in result

    def test_cwd_is_used(self, tmp_path):
        """Test that the command runs in the given working directory."""
        result = self.tool.run(command="pwd", cwd=str(tmp_path))

        assert str(tmp_path) in result

    def test_nonexistent_cwd(self, tmp_path):
        """Test that a missing working directory returns an error."""
        missing = tmp_path / "missing"
        result = self.tool.run(command="echo hi", cwd=str(missing))

        assert "Error: Directory" in result
        assert "does not exist" in result

    def test_cwd_is_file(self, tmp_path):
        """Test that a file passed as cwd returns an error."""
        file_path = tmp_path / "file.txt"
        file_path.write_text("x", encoding="utf-8")
        result = self.tool.run(command="echo hi", cwd=str(file_path))

        assert "Error: Path" in result
        assert "is not a directory" in result

    def test_missing_command(self):
        """Test calling the tool without a command."""
        result = self.tool.run(command="")

        assert "Error: command is required" in result

    def test_timeout(self, monkeypatch):
        """Test that a timed out command returns an error."""

        def fake_run(*args, **kwargs):
            raise subprocess.TimeoutExpired(cmd="sleep 100", timeout=1)

        monkeypatch.setattr(subprocess, "run", fake_run)
        result = self.tool.run(command="sleep 100", timeout=1)

        assert "Error: Command 'sleep 100' timed out after 1 seconds" in result

    def test_unexpected_exception(self, monkeypatch):
        """Test that unexpected errors are reported instead of raised."""

        def fake_run(*args, **kwargs):
            raise OSError("boom")

        monkeypatch.setattr(subprocess, "run", fake_run)
        result = self.tool.run(command="echo hi")

        assert "Error running command 'echo hi': boom" in result

    def test_long_output_is_truncated(self):
        """Test that very long output is shortened."""
        command = f"python3 -c \"print('A' * {MAX_OUTPUT_CHARS * 2})\""
        result = self.tool.run(command=command)

        assert "...[truncated" in result
        assert len(result) < MAX_OUTPUT_CHARS * 2

    def test_tool_schema_validation(self):
        """Test that the tool has a proper schema definition."""
        assert self.tool.name == "run_command"
        assert self.tool.description is not None

        fields = self.tool.Args.model_fields
        assert "command" in fields
        assert "cwd" in fields
        assert "timeout" in fields

        default_args = self.tool.Args(command="echo hi")
        assert default_args.cwd == "."
        assert default_args.timeout == 60

    def test_registered_in_tool_registry(self):
        """Test that the tool is available to the agent."""
        assert TOOL_REGISTRY["run_command"] is not None
        assert isinstance(TOOL_REGISTRY["run_command"], RunCommandTool)
