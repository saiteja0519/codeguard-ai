import pytest

from app.services.github import GitHubError, parse_repo_url


def test_parse_standard_repository_url():
    assert parse_repo_url(
        "https://github.com/example/project"
    ) == ("example", "project")


def test_parse_git_suffix():
    assert parse_repo_url(
        "https://github.com/example/project.git"
    ) == ("example", "project")


@pytest.mark.parametrize(
    "url",
    [
        "not-a-url",
        "http://github.com/example/project",
        "https://github.com/example",
        "https://github.com/example/project/issues",
        "https://example.com/example/project",
    ],
)
def test_reject_invalid_repository_urls(url):
    with pytest.raises(GitHubError):
        parse_repo_url(url)