from typing import Literal

from pydantic import BaseModel, Field, HttpUrl


class CodeRequest(BaseModel):
    code: str = Field(min_length=1, max_length=250_000)
    filename: str = "snippet.py"
    language: str = "auto"
    bug_description: str = ""
    expected_behavior: str = ""
    actual_behavior: str = ""

class GitHubRequest(BaseModel):
    repository_url: HttpUrl
    branch: str | None = None
    max_files: int = Field(default=50, ge=1, le=80)

class Finding(BaseModel):
    id: str
    title: str
    severity: Literal["Critical", "High", "Medium", "Low", "Info"]
    category: str
    file_path: str
    line: int | None = None
    confidence: float = 0.75
    description: str
    evidence: str = ""
    recommendation: str
    validation_status: str = "Unverified"
    suggested_fix: str = ""

class AnalysisResponse(BaseModel):
    analysis_id: str
    source: str
    language: str
    files_analyzed: int
    findings: list[Finding]
    summary: str
    ai_analysis_used: bool = False
    warnings: list[str] = []

class FixRequest(BaseModel):
    code: str
    finding: Finding
    filename: str = "snippet.py"

class FixResponse(BaseModel):
    original_code: str
    fixed_code: str
    explanation: str
    validation: dict
