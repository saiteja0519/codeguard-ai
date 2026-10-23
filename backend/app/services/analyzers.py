import ast
import hashlib
import re
from pathlib import PurePosixPath
from typing import Any

SUPPORTED = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".java": "java",
    ".go": "go",
    ".rb": "ruby",
    ".php": "php",
    ".sql": "sql",
}

SKIP_PARTS = {
    "node_modules",
    ".git",
    "dist",
    "build",
    ".venv",
    "venv",
    "__pycache__",
    "coverage",
}


def language_for(filename: str, code: str = "") -> str:
    ext = PurePosixPath(filename).suffix.lower()

    if ext in SUPPORTED:
        return SUPPORTED[ext]

    stripped = code.lstrip()

    if stripped.startswith(("def ", "import ", "from ", "class ")):
        return "python"

    if "function " in code or "const " in code or "let " in code:
        return "javascript"

    return "text"


def finding(
    title: str,
    severity: str,
    category: str,
    path: str,
    line: int | None,
    desc: str,
    evidence: str,
    rec: str,
    fix: str = "",
    confidence: float = 0.82,
) -> dict[str, Any]:
    raw = f"{path}:{line}:{title}:{evidence}"

    return {
        "id": hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12],
        "title": title,
        "severity": severity,
        "category": category,
        "file_path": path,
        "line": line,
        "confidence": confidence,
        "description": desc,
        "evidence": evidence[:500],
        "recommendation": rec,
        "validation_status": "Unverified",
        "suggested_fix": fix,
    }


def is_numeric_zero(node: ast.AST) -> bool:
    """Return True for numeric literal zero, but not Boolean False."""
    return (
        isinstance(node, ast.Constant)
        and isinstance(node.value, (int, float))
        and not isinstance(node.value, bool)
        and node.value == 0
    )


def find_zero_division_functions(
    tree: ast.AST,
) -> dict[str, set[int]]:
    """Find functions dividing by one or more positional parameters."""
    result: dict[str, set[int]] = {}

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue

        parameters = [arg.arg for arg in node.args.args]
        risky_indexes: set[int] = set()

        for child in ast.walk(node):
            if (
                isinstance(child, ast.BinOp)
                and isinstance(child.op, (ast.Div, ast.FloorDiv, ast.Mod))
                and isinstance(child.right, ast.Name)
                and child.right.id in parameters
            ):
                risky_indexes.add(parameters.index(child.right.id))

        if risky_indexes:
            result[node.name] = risky_indexes

    return result


def analyze_python(code: str, path: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    lines = code.splitlines()

    try:
        tree = ast.parse(code)

    except SyntaxError as exc:
        line = exc.lineno or 1

        evidence = (
            lines[line - 1]
            if 0 < line <= len(lines)
            else (exc.msg or "Syntax error")
        )

        return [
            finding(
                "Python syntax error",
                "High",
                "Correctness",
                path,
                line,
                f"Python cannot parse this file: {exc.msg}.",
                evidence,
                "Correct the syntax error and run a parser or test suite again.",
                confidence=0.99,
            )
        ]

    risky_functions = find_zero_division_functions(tree)

    # Track simple assignments to literal zero.
    zero_names: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            if is_numeric_zero(node.value):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        zero_names.add(target.id)

            elif isinstance(node.value, ast.Constant):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        zero_names.discard(target.id)

        elif (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
        ):
            if node.value is not None and is_numeric_zero(node.value):
                zero_names.add(node.target.id)

            elif node.value is not None:
                zero_names.discard(node.target.id)

    for node in ast.walk(tree):

        # Detect division, floor division, and modulo by zero.
        if isinstance(node, ast.BinOp) and isinstance(
            node.op, (ast.Div, ast.FloorDiv, ast.Mod)
        ):
            line = node.lineno
            evidence = (
                lines[line - 1].strip()
                if line <= len(lines)
                else ""
            )

            if is_numeric_zero(node.right) or (
                isinstance(node.right, ast.Name)
                and node.right.id in zero_names
            ):
                out.append(
                    finding(
                        "Potential division by zero",
                        "High",
                        "Correctness",
                        path,
                        line,
                        "The denominator is zero or is assigned the literal "
                        "zero, so this operation may fail.",
                        evidence,
                        "Validate the denominator before the operation and "
                        "handle the zero case.",
                        confidence=0.98,
                    )
                )

            elif (
                isinstance(node.right, ast.Call)
                and isinstance(node.right.func, ast.Name)
                and node.right.func.id == "len"
            ):
                out.append(
                    finding(
                        "Potential division by zero",
                        "Medium",
                        "Correctness",
                        path,
                        line,
                        "Dividing by len(...) can fail when the collection "
                        "is empty.",
                        evidence,
                        "Check that the collection is non-empty before "
                        "dividing.",
                        confidence=0.70,
                    )
                )

        # Detect a local function call that passes zero to a risky parameter.
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            risky_indexes = risky_functions.get(node.func.id, set())

            for index in risky_indexes:
                if (
                    index < len(node.args)
                    and is_numeric_zero(node.args[index])
                ):
                    line = node.lineno
                    evidence = (
                        lines[line - 1].strip()
                        if line <= len(lines)
                        else ""
                    )

                    out.append(
                        finding(
                            "Potential division by zero",
                            "High",
                            "Correctness",
                            path,
                            line,
                            f"Function '{node.func.id}' divides by a "
                            "parameter that receives literal zero here.",
                            evidence,
                            "Pass a non-zero denominator or handle zero "
                            "explicitly.",
                            confidence=0.95,
                        )
                    )
                    break

        # Detect eval().
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "eval"
        ):
            line = node.lineno
            evidence = (
                lines[line - 1].strip()
                if line <= len(lines)
                else ""
            )

            out.append(
                finding(
                    "Dynamic eval usage",
                    "High",
                    "Security",
                    path,
                    line,
                    "eval executes dynamically constructed Python "
                    "expressions and may enable code execution if input "
                    "is untrusted.",
                    evidence,
                    "Avoid eval; use a safe parser or an explicit mapping "
                    "of allowed operations.",
                    confidence=0.92,
                )
            )

        # Detect exec().
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "exec"
        ):
            line = node.lineno
            evidence = (
                lines[line - 1].strip()
                if line <= len(lines)
                else ""
            )

            out.append(
                finding(
                    "Dynamic exec usage",
                    "High",
                    "Security",
                    path,
                    line,
                    "exec runs dynamically supplied Python code and is "
                    "dangerous with untrusted input.",
                    evidence,
                    "Replace dynamic execution with explicit, constrained "
                    "logic.",
                    confidence=0.90,
                )
            )

        # Detect bare except.
        if isinstance(node, ast.ExceptHandler) and node.type is None:
            line = node.lineno
            evidence = (
                lines[line - 1].strip()
                if line <= len(lines)
                else ""
            )

            out.append(
                finding(
                    "Bare except catches all exceptions",
                    "Low",
                    "Reliability",
                    path,
                    line,
                    "A bare except can hide programming errors and "
                    "system-exiting exceptions.",
                    evidence,
                    "Catch specific exception types and handle them "
                    "deliberately.",
                    confidence=0.88,
                )
            )

        # Detect redundant comparisons with True.
        if (
            isinstance(node, ast.Compare)
            and any(
                isinstance(op, (ast.Eq, ast.NotEq))
                for op in node.ops
            )
            and any(
                isinstance(item, ast.Constant) and item.value is True
                for item in node.comparators
            )
        ):
            line = node.lineno
            evidence = (
                lines[line - 1].strip()
                if line <= len(lines)
                else ""
            )

            out.append(
                finding(
                    "Redundant boolean comparison",
                    "Info",
                    "Maintainability",
                    path,
                    line,
                    "Comparing an expression directly with True is often "
                    "unnecessary and can obscure intent.",
                    evidence,
                    "Consider using the expression directly when its "
                    "truthiness is intended.",
                    confidence=0.62,
                )
            )

    # Detect mutable default arguments.
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            defaults = node.args.defaults + [
                default
                for default in node.args.kw_defaults
                if default is not None
            ]

            for default in defaults:
                if isinstance(default, (ast.List, ast.Dict, ast.Set)):
                    line = getattr(default, "lineno", node.lineno)

                    evidence = (
                        lines[line - 1].strip()
                        if line <= len(lines)
                        else ""
                    )

                    out.append(
                        finding(
                            "Mutable default argument",
                            "Medium",
                            "Correctness",
                            path,
                            line,
                            "A mutable default object is shared across "
                            "calls, which can cause state to leak between "
                            "invocations.",
                            evidence,
                            "Use None as the default and create a new "
                            "object inside the function.",
                            confidence=0.90,
                        )
                    )

    return dedupe(out)


def analyze_generic(
    code: str,
    path: str,
    language: str,
) -> list[dict[str, Any]]:
    """Run lightweight regex checks for non-Python languages."""
    out: list[dict[str, Any]] = []
    lines = code.splitlines()

    patterns = [
        (
            r"\beval\s*\(",
            "Dynamic evaluation detected",
            "High",
            "Security",
            (
                "Avoid evaluating untrusted strings; use a safe parser "
                "or explicit logic."
            ),
        ),
        (
            r"\b(password|api_key|secret)\s*=\s*(['\"])[^'\"]{6,}\2",
            "Possible hard-coded secret",
            "High",
            "Security",
            (
                "Move secrets to environment variables or a secret manager "
                "and rotate exposed credentials."
            ),
        ),
        (
            r"\bSELECT\b.*\+\s*\w+",
            "Possible SQL query concatenation",
            "Medium",
            "Security",
            "Use parameterized queries rather than string concatenation.",
        ),
        (
            r"\bconsole\.log\s*\(",
            "Debug logging left in code",
            "Info",
            "Maintainability",
            (
                "Remove or replace debug logging with the application logger "
                "where appropriate."
            ),
        ),
        (
            r"\bTODO\b|\bFIXME\b",
            "Unresolved TODO/FIXME marker",
            "Info",
            "Maintainability",
            (
                "Confirm whether this marker represents unfinished "
                "production work."
            ),
        ),
    ]

    for line_number, line in enumerate(lines, 1):
        for pattern, title, severity, category, recommendation in patterns:
            if re.search(pattern, line, re.IGNORECASE):
                out.append(
                    finding(
                        title,
                        severity,
                        category,
                        path,
                        line_number,
                        "A heuristic pattern matched this line. Review the "
                        "surrounding context before treating it as a "
                        "confirmed defect.",
                        line.strip(),
                        recommendation,
                        confidence=0.55,
                    )
                )

    return dedupe(out)


def dedupe(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[Any, ...]] = set()
    result: list[dict[str, Any]] = []

    for item in items:
        key = (
            item["title"],
            item["file_path"],
            item.get("line"),
        )

        if key not in seen:
            seen.add(key)
            result.append(item)

    return result


def analyze_file(path: str, code: str) -> list[dict[str, Any]]:
    language = language_for(path, code)

    if language == "python":
        return analyze_python(code, path)

    return analyze_generic(code, path, language)