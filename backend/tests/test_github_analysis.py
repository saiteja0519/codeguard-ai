
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.github import GitHubError


client = TestClient(app)


def mock_repository():
    """Return a fake repository without making a network request."""
    return {
        "owner": "test-owner",
        "repo": "test-repo",
        "branch": "main",
        "html_url": "https://github.com/test-owner/test-repo",
        "files": [
            {
                "path": "example.py",
                "code": (
                    "def add(a, b):\n"
                    "    return a + b\n"
                ),
            }
        ],
        "warnings": [],
    }


def test_github_analysis_success(monkeypatch):
    async def fake_fetch_repository(
        url,
        branch=None,
        max_files=50,
    ):
        return mock_repository()

    monkeypatch.setattr(
        "app.main.fetch_repository",
        fake_fetch_repository,
    )

    response = client.post(
        "/api/v1/analyses/github",
        json={
            "repository_url": (
                "https://github.com/test-owner/test-repo"
            ),
            "branch": "main",
            "max_files": 10,
        },
    )

    assert response.status_code == 200

    result = response.json()

    assert result["source"] == "github:test-owner/test-repo@main"
    assert result["repository_url"] == (
        "https://github.com/test-owner/test-repo"
    )
    assert result["branch"] == "main"
    assert result["files_analyzed"] == 1
    assert "findings" in result


def test_github_analysis_handles_repository_error(monkeypatch):
    async def fake_fetch_repository(
        url,
        branch=None,
        max_files=50,
    ):
        raise GitHubError("Repository not found or private.")

    monkeypatch.setattr(
        "app.main.fetch_repository",
        fake_fetch_repository,
    )

    response = client.post(
        "/api/v1/analyses/github",
        json={
            "repository_url": (
                "https://github.com/test-owner/missing-repo"
            ),
            "branch": "main",
            "max_files": 10,
        },
    )

    assert response.status_code == 400
    assert "Repository not found or private" in (
        response.json()["detail"]
    )


def test_github_analysis_rejects_invalid_repository_url():
    response = client.post(
        "/api/v1/analyses/github",
        json={
            "repository_url": "not-a-valid-url",
            "branch": "main",
            "max_files": 10,
        },
    )

    assert response.status_code == 422
