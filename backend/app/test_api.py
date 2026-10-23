
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_endpoint():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_analyze_code_endpoint():
    response = client.post(
        "/api/v1/analyses/code",
        json={
            "filename": "example.py",
            "code": "def add(a, b):\n    return a + b\n",
            "bug_description": "",
            "expected_behavior": "",
            "actual_behavior": "",
        },
    )

    assert response.status_code == 200
    result = response.json()
    assert "findings" in result
    assert result["files_analyzed"] == 1


def test_fix_endpoint_handles_unsupported_fix():
    response = client.post(
        "/api/v1/findings/fix",
        json={
            "filename": "example.py",
            "code": "print('hello')\n",
            "finding": {
                "title": "Unsupported test finding",
                "severity": "Low",
                "category": "Test",
                "file_path": "example.py",
                "line": 1,
                "confidence": 0.5,
                "description": "A test finding with no matching local fix rule.",
                "evidence": "print('hello')",
                "recommendation": "Review manually.",
                "suggested_fix": "",
            },
        },
    )

    assert response.status_code == 422
