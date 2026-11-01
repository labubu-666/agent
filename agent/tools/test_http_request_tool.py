import requests

from agent.tools import TOOL_REGISTRY
from agent.tools.http import DEFAULT_TIMEOUT, HttpRequestTool
from agent.tools.shell import MAX_OUTPUT_CHARS


class FakeResponse:
    """A minimal stand-in for requests.Response."""

    def __init__(self, status_code=200, reason="OK", headers=None, text=""):
        self.status_code = status_code
        self.reason = reason
        self.headers = headers or {}
        self.text = text


class TestHttpRequestTool:
    """Test cases for the HttpRequestTool."""

    def setup_method(self):
        """Set up test fixtures before each test method."""
        self.tool = HttpRequestTool()

    def test_successful_get(self, monkeypatch):
        """Test that status, headers and body are returned."""

        def fake_request(*args, **kwargs):
            return FakeResponse(
                headers={"Content-Type": "text/plain"}, text="hello world"
            )

        monkeypatch.setattr(requests, "request", fake_request)
        result = self.tool.run(url="https://example.com")

        assert "Status: 200 OK" in result
        assert "Content-Type: text/plain" in result
        assert "BODY:\nhello world" in result

    def test_default_timeout_is_three_seconds(self, monkeypatch):
        """Test that requests are made with a 3 second timeout by default."""
        captured = {}

        def fake_request(*args, **kwargs):
            captured.update(kwargs)
            return FakeResponse()

        monkeypatch.setattr(requests, "request", fake_request)
        self.tool.run(url="https://example.com")

        assert DEFAULT_TIMEOUT == 3
        assert captured["timeout"] == 3

    def test_custom_arguments_are_passed(self, monkeypatch):
        """Test that method, headers, params and bodies are forwarded."""
        captured = {}

        def fake_request(method, url, **kwargs):
            captured["method"] = method
            captured["url"] = url
            captured.update(kwargs)
            return FakeResponse(status_code=201, reason="Created")

        monkeypatch.setattr(requests, "request", fake_request)
        result = self.tool.run(
            url="https://example.com/api",
            method="post",
            headers={"Authorization": "Bearer x"},
            params={"q": "1"},
            json_body={"name": "agent"},
            timeout=10,
        )

        assert captured["method"] == "POST"
        assert captured["url"] == "https://example.com/api"
        assert captured["headers"] == {"Authorization": "Bearer x"}
        assert captured["params"] == {"q": "1"}
        assert captured["json"] == {"name": "agent"}
        assert captured["timeout"] == 10
        assert "Status: 201 Created" in result

    def test_timeout_error(self, monkeypatch):
        """Test that a request timeout returns an error message."""

        def fake_request(*args, **kwargs):
            raise requests.Timeout("slow")

        monkeypatch.setattr(requests, "request", fake_request)
        result = self.tool.run(url="https://example.com")

        assert "Error: Request to 'https://example.com' timed out after 3" in result

    def test_request_exception(self, monkeypatch):
        """Test that other request errors are reported instead of raised."""

        def fake_request(*args, **kwargs):
            raise requests.ConnectionError("refused")

        monkeypatch.setattr(requests, "request", fake_request)
        result = self.tool.run(url="https://example.com")

        assert "Error making request to 'https://example.com'" in result
        assert "refused" in result

    def test_missing_url(self):
        """Test calling the tool without a URL."""
        result = self.tool.run(url="")

        assert "Error: url is required" in result

    def test_long_body_is_truncated(self, monkeypatch):
        """Test that very long response bodies are shortened."""

        def fake_request(*args, **kwargs):
            return FakeResponse(text="A" * (MAX_OUTPUT_CHARS * 2))

        monkeypatch.setattr(requests, "request", fake_request)
        result = self.tool.run(url="https://example.com")

        assert "...[truncated" in result
        assert len(result) < MAX_OUTPUT_CHARS * 2

    def test_tool_schema_validation(self):
        """Test that the tool has a proper schema definition."""
        assert self.tool.name == "http_request"
        assert self.tool.description is not None

        fields = self.tool.Args.model_fields
        for field in [
            "url",
            "method",
            "headers",
            "params",
            "body",
            "json_body",
            "timeout",
        ]:
            assert field in fields

        default_args = self.tool.Args(url="https://example.com")
        assert default_args.method == "GET"
        assert default_args.timeout == 3

    def test_registered_in_tool_registry(self):
        """Test that the tool is available to the agent."""
        assert TOOL_REGISTRY["http_request"] is not None
        assert isinstance(TOOL_REGISTRY["http_request"], HttpRequestTool)
