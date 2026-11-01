from typing import Any

import requests
from pydantic import BaseModel, Field

from .base import Tool
from .shell import _truncate

DEFAULT_TIMEOUT = 3


class HttpRequestTool(Tool):
    """A tool to make HTTP requests and return the response status, headers and body."""

    name = "http_request"
    description = (
        "Makes an HTTP request to a URL and returns the status code, response headers "
        "and response body. Useful for calling APIs or fetching web pages."
    )

    class Args(BaseModel):
        url: str = Field(..., description="The URL to request.")
        method: str = Field(
            default="GET",
            description="The HTTP method to use, e.g. GET, POST, PUT, DELETE. Defaults to GET.",
        )
        headers: dict[str, str] | None = Field(
            default=None, description="Optional HTTP headers to send."
        )
        params: dict[str, str] | None = Field(
            default=None, description="Optional query string parameters."
        )
        body: str | None = Field(
            default=None, description="Optional raw request body as text."
        )
        json_body: dict[str, Any] | list[Any] | None = Field(
            default=None,
            description="Optional JSON request body. Sent with a JSON content type.",
        )
        timeout: float = Field(
            default=DEFAULT_TIMEOUT,
            description=f"Maximum number of seconds to wait for the response. Defaults to {DEFAULT_TIMEOUT}.",
        )

    args_schema = Args

    def run(self, **kwargs: Any) -> str:
        url = kwargs.get("url", "")
        method = kwargs.get("method") or "GET"
        headers = kwargs.get("headers")
        params = kwargs.get("params")
        body = kwargs.get("body")
        json_body = kwargs.get("json_body")
        timeout = kwargs.get("timeout", DEFAULT_TIMEOUT)
        if not url:
            return "Error: url is required."

        try:
            response = requests.request(
                method.upper(),
                url,
                headers=headers,
                params=params,
                data=body,
                json=json_body,
                timeout=timeout,
            )
        except requests.Timeout:
            return f"Error: Request to '{url}' timed out after {timeout} seconds."
        except requests.RequestException as e:
            return f"Error making request to '{url}': {e}"

        response_headers = "\n".join(
            f"{key}: {value}" for key, value in response.headers.items()
        )
        return (
            f"Status: {response.status_code} {response.reason}\n\n"
            f"HEADERS:\n{response_headers}\n\n"
            f"BODY:\n{_truncate(response.text)}"
        )
