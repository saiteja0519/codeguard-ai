import ast
import hashlib
import io
import zipfile
from pathlib import PurePosixPath
from uuid import uuid4

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.schemas import CodeRequest, FixRequest, GitHubRequest
from app.services.ai_review import generate_fix, review_with_ai
from app.services.analyzers import (
    SKIP_PARTS,
    analyze_file,
    dedupe,
    language_for,
)
from app.services.github import GitHubError, fetch_repository

app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    description="Code review and bug detection API with optional AI support",
)


# Allow the local frontend origins used during development.
FRONTEND_ORIGINS = list(
    dict.fromkeys(
        [
            settings.frontend_origin,
            "http://127.0.0.1:5178",
            "http://localhost:5178",
            "http://127.0.0.1:5173",
            "http://localhost:5173",
            "http://127.0.0.1:5174",
            "http://localhost:5174",
            "http://127.0.0.1:5175",
            "http://localhost:5175",
            "http://127.0.0.1:5179",
            "http://localhost:5179",
            "http://127.0.0.1:5180",
            "http://localhost:5180",
        ]
    )
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=FRONTEND_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "app": settings.app_name,
        "ai_provider": settings.ai_provider,
    }


async def run_analysis(
    files: list[dict],
    source: str,
    user_context: str = "",
    warnings: list[str] | None = None,
):
    if not files:
        raise HTTPException(
            status_code=400,
            detail="No supported source files were found.",
        )

    findings = []
    languages = []

    for file_item in files:
        languages.append(
            language_for(file_item["path"], file_item["code"])
        )
        findings.extend(
            analyze_file(file_item["path"], file_item["code"])
        )

    ai_used = False
    summary = (
        f"Analyzed {len(files)} file(s) "
        "with local heuristic/static checks."
    )

    ai_files = [
        {
            "path": file_item["path"],
            "code": file_item["code"][:18000],
        }
        for file_item in files[:12]
    ]

    warning_list = warnings if warnings is not None else []

    # AI review is optional. Static analysis remains available without keys.
    try:
        ai_result = await review_with_ai(ai_files, user_context)

        if ai_result:
            ai_used = True
            summary = str(ai_result.get("summary") or summary)

            valid_paths = {
                file_item["path"] for file_item in files
            }

            for item in ai_result.get("findings", [])[:80]:
                if not isinstance(item, dict):
                    continue

                path = str(item.get("file_path", ""))

                if path not in valid_paths:
                    continue

                line = item.get("line")
                if not isinstance(line, int) or isinstance(line, bool):
                    line = None

                severity = item.get("severity", "Medium")
                if severity not in {
                    "Critical",
                    "High",
                    "Medium",
                    "Low",
                    "Info",
                }:
                    severity = "Medium"

                try:
                    confidence = max(
                        0.0,
                        min(1.0, float(item.get("confidence", 0.65))),
                    )
                except (TypeError, ValueError):
                    confidence = 0.65

                raw = (
                    f"ai:{path}:{line}:"
                    f"{item.get('title', 'Finding')}:"
                    f"{item.get('evidence', '')}"
                )

                findings.append(
                    {
                        "id": hashlib.sha1(
                            raw.encode("utf-8")
                        ).hexdigest()[:12],
                        "title": str(
                            item.get("title", "Potential issue")
                        )[:160],
                        "severity": severity,
                        "category": str(
                            item.get("category", "Correctness")
                        )[:80],
                        "file_path": path,
                        "line": line,
                        "confidence": confidence,
                        "description": str(
                            item.get("description", "")
                        )[:1500],
                        "evidence": str(
                            item.get("evidence", "")
                        )[:500],
                        "recommendation": str(
                            item.get(
                                "recommendation",
                                "Review the surrounding context.",
                            )
                        )[:1000],
                        "validation_status": "Unverified",
                        "suggested_fix": str(
                            item.get("suggested_fix", "")
                        )[:4000],
                    }
                )

    except Exception as exc:  # noqa: BLE001
        warning_list.append(
            "AI review was unavailable: "
            f"{type(exc).__name__}. "
            "Static analysis results are still available."
        )

    findings = dedupe(findings)

    severity_order = {
        "Critical": 0,
        "High": 1,
        "Medium": 2,
        "Low": 3,
        "Info": 4,
    }

    findings.sort(
        key=lambda finding: (
            severity_order.get(finding.get("severity"), 5),
            -finding.get("confidence", 0),
        )
    )

    language = (
        max(set(languages), key=languages.count)
        if languages
        else "text"
    )

    return {
        "analysis_id": str(uuid4()),
        "source": source,
        "language": language,
        "files_analyzed": len(files),
        "findings": findings,
        "summary": summary,
        "ai_analysis_used": ai_used,
        "warnings": warning_list,
    }


@app.post("/api/v1/analyses/code")
async def analyze_code(req: CodeRequest):
    context_parts = [
        req.bug_description,
        (
            f"Expected: {req.expected_behavior}"
            if req.expected_behavior
            else ""
        ),
        (
            f"Actual: {req.actual_behavior}"
            if req.actual_behavior
            else ""
        ),
    ]

    context = "\n".join(
        part for part in context_parts if part
    )

    filename = (
        req.filename.replace("\\", "/").split("/")[-1]
        or "snippet.txt"
    )

    return await run_analysis(
        [{"path": filename, "code": req.code}],
        "pasted_code",
        context,
    )


@app.post("/api/v1/analyses/github")
async def analyze_github(req: GitHubRequest):
    try:
        repo = await fetch_repository(
            str(req.repository_url),
            req.branch,
            req.max_files,
        )
    except GitHubError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    result = await run_analysis(
        repo["files"],
        (
            f"github:{repo['owner']}/"
            f"{repo['repo']}@{repo['branch']}"
        ),
        warnings=repo["warnings"],
    )

    result["repository_url"] = repo["html_url"]
    result["branch"] = repo["branch"]

    return result


@app.post("/api/v1/analyses/upload")
async def analyze_upload(file: UploadFile = File(...)):  # noqa: B008
    raw = await file.read(settings.max_total_bytes + 1)

    if len(raw) > settings.max_total_bytes:
        raise HTTPException(
            status_code=413,
            detail="Upload exceeds the configured total-size limit.",
        )

    files = []
    warnings = []

    filename = (file.filename or "uploaded.txt").replace("\\", "/")
    filename = filename.split("/")[-1] or "uploaded.txt"

    if filename.lower().endswith(".zip"):
        try:
            archive = zipfile.ZipFile(io.BytesIO(raw))
        except zipfile.BadZipFile as exc:
            raise HTTPException(
                status_code=400,
                detail="Uploaded ZIP archive is invalid.",
            ) from exc

        try:
            total = 0

            supported_extensions = {
                ".py",
                ".js",
                ".jsx",
                ".ts",
                ".tsx",
                ".java",
                ".go",
                ".rb",
                ".php",
                ".sql",
                ".json",
                ".yaml",
                ".yml",
                ".toml",
            }

            for info in archive.infolist():
                path = PurePosixPath(info.filename)

                if path.is_absolute() or ".." in path.parts:
                    continue

                if info.is_dir() or set(path.parts) & SKIP_PARTS:
                    continue

                if info.file_size > settings.max_file_bytes:
                    warnings.append(
                        f"Skipped oversized file: {info.filename}"
                    )
                    continue

                if path.suffix.lower() not in supported_extensions:
                    continue

                if len(files) >= settings.max_files:
                    warnings.append("File count limit reached.")
                    break

                if total + info.file_size > settings.max_total_bytes:
                    warnings.append("Archive content limit reached.")
                    break

                try:
                    content = archive.read(info).decode("utf-8")
                except (UnicodeDecodeError, KeyError, RuntimeError):
                    warnings.append(
                        f"Skipped unreadable file: {info.filename}"
                    )
                    continue

                total += info.file_size
                files.append(
                    {
                        "path": str(path),
                        "code": content,
                    }
                )
        finally:
            archive.close()

    else:
        if len(raw) > settings.max_file_bytes:
            raise HTTPException(
                status_code=413,
                detail="File exceeds the configured per-file size limit.",
            )

        try:
            content = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise HTTPException(
                status_code=400,
                detail="Only UTF-8 text source files are supported.",
            ) from exc

        files = [{"path": filename, "code": content}]

    result = await run_analysis(
        files,
        "upload",
        warnings=warnings,
    )

    result["upload_name"] = file.filename

    return result


@app.post("/api/v1/findings/fix")
async def fix_finding(req: FixRequest):
    """
    Generate a supported local fix first, then use an optional configured
    AI provider. No API key is required for supported local rules.
    """
    try:
        generated = await generate_fix(
            req.code,
            req.filename,
            req.finding.model_dump(),
        )
    except Exception as exc:
        # Keep secret values and provider response bodies out of the response.
        raise HTTPException(
            status_code=502,
            detail=(
                "Fix generation failed. "
                f"Error type: {type(exc).__name__}. "
                "Check backend logs for diagnostics."
            ),
        ) from exc

    if not generated:
        raise HTTPException(
            status_code=422,
            detail=(
                "No safe fix is available for this finding in local mode. "
                "Review the code manually or add a tested rule for this pattern."
            ),
        )

    fixed, explanation = generated

    validation = {
        "status": "not_run",
        "message": (
            "No code was executed. Review the patch and run "
            "your project tests in an isolated environment."
        ),
    }

    if language_for(req.filename, fixed) == "python":
        try:
            ast.parse(fixed)
            validation = {
                "status": "syntax_passed",
                "message": (
                    "Python syntax parsing passed. "
                    "This does not prove the fix is correct."
                ),
            }
        except SyntaxError as exc:
            validation = {
                "status": "syntax_failed",
                "message": (
                    f"Generated patch has a syntax error on "
                    f"line {exc.lineno}: {exc.msg}"
                ),
            }

    return {
        "original_code": req.code,
        "fixed_code": fixed,
        "explanation": explanation,
        "validation": validation,
    }


@app.exception_handler(Exception)
async def unexpected_error_handler(request, exc):
    # Keep internal exception details out of client responses.
    return JSONResponse(
        status_code=500,
        content={
            "detail": (
                "Unexpected server error. "
                "Check backend logs for a sanitized diagnostic."
            )
        },
    )