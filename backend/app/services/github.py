
import base64
import binascii
import re
from urllib.parse import quote

import httpx

from app.config import settings
from app.services.analyzers import SKIP_PARTS


class GitHubError(Exception):
    """Safe, user-facing GitHub integration error."""


ALLOWED_EXTENSIONS = {
    ".py", ".js", ".jsx", ".ts", ".tsx",
    ".java", ".go", ".rb", ".php", ".sql",
    ".json", ".yaml", ".yml", ".toml",
}


def parse_repo_url(url: str) -> tuple[str, str]:
    """Accept only a standard GitHub owner/repository URL."""
    pattern = (
        r"https://github\.com/"
        r"([A-Za-z0-9_.-]+)/"
        r"([A-Za-z0-9_.-]+?)(?:\.git)?/?"
    )
    match = re.fullmatch(pattern, url.strip(), re.IGNORECASE)

    if not match:
        raise GitHubError(
            "Enter a valid GitHub repository URL, "
            "such as https://github.com/owner/repo."
        )

    owner, repo = match.groups()

    if owner in {".", ".."} or repo in {".", ".."}:
        raise GitHubError("Invalid GitHub repository owner or name.")

    return owner, repo


def _check_response(response: httpx.Response, context: str) -> None:
    """Convert GitHub HTTP errors to safe application messages."""
    if response.status_code == 404:
        raise GitHubError(
            f"{context}: repository, branch, or resource not found. "
            "Check the URL and branch. Private repositories require "
            "an authorized GITHUB_TOKEN."
        )

    if response.status_code in (403, 429):
        raise GitHubError(
            "GitHub denied the request or rate limit was reached. "
            "Try again later or configure an authorized GITHUB_TOKEN."
        )

    if response.status_code >= 400:
        raise GitHubError(
            f"{context}: GitHub returned HTTP {response.status_code}."
        )


async def fetch_repository(
    url: str,
    branch: str | None = None,
    max_files: int = 50,
) -> dict:
    """Fetch bounded source files from a GitHub repository."""
    owner, repo = parse_repo_url(url)

    file_limit = min(max_files, settings.max_files)
    if file_limit < 1:
        raise GitHubError("The file limit must be at least 1.")

    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "CodeGuard-AI",
    }

    if settings.github_token:
        headers["Authorization"] = f"Bearer {settings.github_token}"

    base_url = f"https://api.github.com/repos/{owner}/{repo}"

    try:
        async with httpx.AsyncClient(
            timeout=20,
            follow_redirects=False,
        ) as client:
            metadata_response = await client.get(
                base_url,
                headers=headers,
            )
            _check_response(metadata_response, "Repository lookup")

            metadata = metadata_response.json()
            selected_branch = branch or metadata.get("default_branch")

            if (
                not isinstance(selected_branch, str)
                or not selected_branch.strip()
            ):
                raise GitHubError(
                    "GitHub did not provide a valid default branch."
                )

            encoded_branch = quote(selected_branch, safe="")
            tree_url = (
                f"{base_url}/git/trees/{encoded_branch}?recursive=1"
            )

            tree_response = await client.get(
                tree_url,
                headers=headers,
            )
            _check_response(tree_response, "Repository tree lookup")

            tree_data = tree_response.json()
            if not isinstance(tree_data, dict):
                raise GitHubError("GitHub returned an invalid repository tree.")

            tree = tree_data.get("tree")
            if not isinstance(tree, list):
                raise GitHubError("GitHub returned an invalid repository tree.")

            candidates = []

            for item in tree:
                if not isinstance(item, dict):
                    continue

                if item.get("type") != "blob":
                    continue

                path = item.get("path")
                if not isinstance(path, str) or not path:
                    continue

                if path.startswith("/") or "\\" in path:
                    continue

                parts = set(path.split("/"))
                if ".." in parts or parts & SKIP_PARTS:
                    continue

                if not any(
                    path.lower().endswith(ext)
                    for ext in ALLOWED_EXTENSIONS
                ):
                    continue

                size = item.get("size")
                if not isinstance(size, int) or size < 0:
                    continue

                if size > settings.max_file_bytes:
                    continue

                # Use a URL constructed from our validated repository
                # and path, not a URL supplied by an API response.
                candidates.append((path, size))

            files = []
            warnings = []
            total_bytes = 0

            for path, _size in candidates[:file_limit]:
                if total_bytes >= settings.max_total_bytes:
                    warnings.append(
                        "Total repository source size limit reached."
                    )
                    break

                encoded_path = quote(path, safe="/")
                contents_url = (
                    f"{base_url}/contents/{encoded_path}"
                    f"?ref={quote(selected_branch, safe='')}"
                )

                response = await client.get(
                    contents_url,
                    headers=headers,
                )

                if response.status_code != 200:
                    warnings.append(
                        f"Could not retrieve {path} "
                        f"(HTTP {response.status_code})."
                    )
                    continue

                try:
                    data = response.json()
                except ValueError:
                    warnings.append(f"Invalid API response for {path}.")
                    continue

                if (
                    not isinstance(data, dict)
                    or data.get("encoding") != "base64"
                ):
                    warnings.append(
                        f"Unsupported content response for {path}."
                    )
                    continue

                encoded_content = data.get("content")
                if not isinstance(encoded_content, str):
                    warnings.append(f"Missing file content for {path}.")
                    continue

                try:
                    content_bytes = base64.b64decode(
                        encoded_content,
                        validate=True,
                    )
                    content = content_bytes.decode("utf-8")
                except (
                    binascii.Error,
                    UnicodeDecodeError,
                    ValueError,
                ):
                    warnings.append(
                        f"Skipped invalid UTF-8/Base64 file: {path}."
                    )
                    continue

                if len(content_bytes) > settings.max_file_bytes:
                    warnings.append(f"Skipped oversized file: {path}.")
                    continue

                if (
                    total_bytes + len(content_bytes)
                    > settings.max_total_bytes
                ):
                    warnings.append(
                        "Total repository source size limit reached."
                    )
                    break

                total_bytes += len(content_bytes)
                files.append({"path": path, "code": content})

            if len(candidates) > len(files):
                warnings.append(
                    f"Analyzed {len(files)} files; repository limits "
                    "or retrieval failures may have excluded additional files."
                )

            return {
                "owner": owner,
                "repo": repo,
                "branch": selected_branch,
                "files": files,
                "warnings": warnings,
                "html_url": metadata.get(
                    "html_url",
                    f"https://github.com/{owner}/{repo}",
                ),
            }

    except GitHubError:
        raise
    except httpx.TimeoutException as exc:
        raise GitHubError(
            "GitHub request timed out. Please try again."
        ) from exc
    except httpx.RequestError as exc:
        raise GitHubError(
            "Could not connect to GitHub. Check your network and retry."
        ) from exc
    except (ValueError, TypeError) as exc:
        raise GitHubError(
            "GitHub returned an unexpected response."
        ) from exc
