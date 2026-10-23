from app.services.analyzers import analyze_file, language_for


def test_python_syntax_error_is_reported():
    findings = analyze_file("broken.py", "def hello(:\n    pass")
    assert any(f["title"] == "Python syntax error" for f in findings)


def test_mutable_default_is_reported():
    findings = analyze_file("example.py", "def add_item(item, items=[]):\n    items.append(item)\n    return items\n")
    assert any(f["title"] == "Mutable default argument" for f in findings)


def test_eval_is_reported():
    findings = analyze_file("example.py", "result = eval(user_input)\n")
    assert any("eval" in f["title"].lower() for f in findings)


def test_language_detection():
    assert language_for("app.py") == "python"
    assert language_for("index.ts") == "typescript"

def test_literal_division_by_zero_is_reported():
    findings = analyze_file("example.py", "result = 10 / 0\n")
    assert any(
        f["title"] == "Potential division by zero"
        for f in findings
    )


def test_function_called_with_zero_denominator_is_reported():
    code = (
        "def divide(a, b):\n"
        "    return a / b\n"
        "\n"
        "print(divide(10, 0))\n"
    )
    findings = analyze_file("example.py", code)
    assert any(
        f["title"] == "Potential division by zero"
        for f in findings
    )


def test_nonzero_literal_division_is_not_flagged():
    findings = analyze_file("example.py", "result = 10 / 2\n")
    assert not any(
        f["title"] == "Potential division by zero"
        for f in findings
    )

