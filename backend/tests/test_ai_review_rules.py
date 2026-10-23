from app.services.ai_review import generate_local_fix


def test_empty_average_gets_local_fix():
    code = (
        "def average(numbers):\n"
        "    return sum(numbers) / len(numbers)\n"
    )

    finding = {
        "title": "Division by zero",
        "description": "Division by zero when numbers is empty",
        "category": "Correctness",
    }

    result = generate_local_fix(code, "example.py", finding)

    assert result is not None

    fixed_code, explanation = result

    assert "if not numbers:" in fixed_code
    assert 'raise ValueError("Cannot calculate an average of an empty collection")' in fixed_code
    assert "return sum(numbers) / len(numbers)" in fixed_code
    assert explanation


def test_unsupported_code_returns_no_local_fix():
    code = "print('hello')\n"

    finding = {
        "title": "Unsupported test finding",
        "description": "No matching local rule",
        "category": "Test",
    }

    result = generate_local_fix(code, "example.py", finding)

    assert result is None
