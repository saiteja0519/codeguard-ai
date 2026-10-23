
from io import BytesIO
from zipfile import ZipFile

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def create_zip(files: dict[str, str]) -> bytes:
    """Create an in-memory ZIP archive for upload tests."""
    buffer = BytesIO()

    with ZipFile(buffer, "w") as archive:
        for filename, content in files.items():
            archive.writestr(filename, content)

    return buffer.getvalue()


def upload_zip(filename: str, content: bytes):
    """Upload ZIP bytes to the CodeGuard AI analysis endpoint."""
    return client.post(
        "/api/v1/analyses/upload",
        files={
            "file": (
                filename,
                content,
                "application/zip",
            )
        },
    )


def test_upload_valid_python_zip():
    zip_content = create_zip(
        {
            "example.py": (
                "def add(a, b):\n"
                "    return a + b\n"
            )
        }
    )

    response = upload_zip("source.zip", zip_content)

    assert response.status_code == 200

    result = response.json()
    assert result["files_analyzed"] == 1
    assert "findings" in result
    assert result["source"] == "upload"
    assert result["upload_name"] == "source.zip"


def test_upload_invalid_zip_is_rejected():
    response = upload_zip(
        "broken.zip",
        b"this is not a valid ZIP archive",
    )

    assert response.status_code == 400
    assert "invalid" in response.json()["detail"].lower()


def test_zip_parent_traversal_path_is_skipped():
    zip_content = create_zip(
        {
            "../outside.py": "print('should not be analyzed')\n",
            "safe.py": (
                "def add(a, b):\n"
                "    return a + b\n"
            ),
        }
    )

    response = upload_zip("source.zip", zip_content)

    assert response.status_code == 200
    assert response.json()["files_analyzed"] == 1


def test_zip_with_no_supported_source_files_returns_error():
    zip_content = create_zip(
        {
            "README.md": "# Example project\n",
            "notes.txt": "No supported source code here.\n",
        }
    )

    response = upload_zip("docs.zip", zip_content)

    assert response.status_code == 400
    assert "supported source files" in response.json()["detail"].lower()
