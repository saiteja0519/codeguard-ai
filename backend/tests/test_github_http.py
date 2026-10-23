
import base64

import httpx
import pytest

from app.services.github import GitHubError, fetch_repository


@pytest.fixture
def anyio_backend():
    """Run async tests using asyncio through the AnyIO plugin."""
    return "asyncio"


class MockAsyncClient:
    """Mock GitHub HTTP responses without network access."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.urls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        return False

    async def get(self, url, headers=None):
        self.urls.append(url)

        if not self.responses:
            raise AssertionError(f"Unexpected HTTP request: {url}")

        mocked_response = self.responses.pop(0)

        if isinstance(mocked_response, Exception):
            raise mocked_response

        return mocked_response


def make_response(status_code, json_data):
    """Create a mock HTTP response."""
    request = httpx.Request(
        "GET",
        "https://api.github.com/test",
    )
    return httpx.Response(
        status_code,
        json=json_data,
        request=request,
    )


@pytest.mark.anyio
async def test_repository_not_found(monkeypatch):
    mock_client = MockAsyncClient([
        make_response(404, {"message": "Not Found"}),
    ])

    monkeypatch.setattr(
        "app.services.github.httpx.AsyncClient",
        lambda **kwargs: mock_client,
    )

    with pytest.raises(GitHubError, match="not found"):
        await fetch_repository(
            "https://github.com/example/missing"
        )


@pytest.mark.anyio
async def test_github_rate_limit(monkeypatch):
    mock_client = MockAsyncClient([
        make_response(429, {"message": "rate limit exceeded"}),
    ])

    monkeypatch.setattr(
        "app.services.github.httpx.AsyncClient",
        lambda **kwargs: mock_client,
    )

    with pytest.raises(GitHubError, match="rate limit"):
        await fetch_repository(
            "https://github.com/example/project"
        )


@pytest.mark.anyio
async def test_invalid_base64_content_is_skipped(monkeypatch):
    mock_client = MockAsyncClient([
        make_response(200, {"default_branch": "main"}),
        make_response(200, {
            "tree": [{
                "type": "blob",
                "path": "example.py",
                "size": 10,
            }]
        }),
        make_response(200, {
            "encoding": "base64",
            "content": "%%%not-base64%%%",
        }),
    ])

    monkeypatch.setattr(
        "app.services.github.httpx.AsyncClient",
        lambda **kwargs: mock_client,
    )

    result = await fetch_repository(
        "https://github.com/example/project"
    )

    assert result["files"] == []
    assert any(
        "invalid UTF-8/Base64" in warning
        for warning in result["warnings"]
    )


@pytest.mark.anyio
async def test_valid_content_is_decoded(monkeypatch):
    source = "def add(a, b):\n    return a + b\n"
    encoded = base64.b64encode(
        source.encode("utf-8")
    ).decode("ascii")

    mock_client = MockAsyncClient([
        make_response(200, {
            "default_branch": "main",
            "html_url": "https://github.com/example/project",
        }),
        make_response(200, {
            "tree": [{
                "type": "blob",
                "path": "example.py",
                "size": len(source.encode("utf-8")),
            }]
        }),
        make_response(200, {
            "encoding": "base64",
            "content": encoded,
        }),
    ])

    monkeypatch.setattr(
        "app.services.github.httpx.AsyncClient",
        lambda **kwargs: mock_client,
    )

    result = await fetch_repository(
        "https://github.com/example/project"
    )

    assert len(result["files"]) == 1
    assert result["files"][0]["path"] == "example.py"
    assert result["files"][0]["code"] == source
    assert result["branch"] == "main"


@pytest.mark.anyio
async def test_network_failure_returns_safe_error(monkeypatch):
    mock_client = MockAsyncClient([
        httpx.ConnectError("mock connection failure"),
    ])

    monkeypatch.setattr(
        "app.services.github.httpx.AsyncClient",
        lambda **kwargs: mock_client,
    )

    with pytest.raises(
        GitHubError,
        match="Could not connect to GitHub",
    ):
        await fetch_repository(
            "https://github.com/example/project"
        )
