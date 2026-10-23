
import { useMemo, useState } from 'react';
import {
  Code2,
  Upload,
  Search,
  ShieldCheck,
  Bug,
  Sparkles,
  FileCode2,
  AlertTriangle,
  CheckCircle2,
  LoaderCircle,
  Copy,
  Download,
  RefreshCw,
} from 'lucide-react';

type Finding = {
  id: string;
  title: string;
  severity: 'Critical' | 'High' | 'Medium' | 'Low' | 'Info';
  category: string;
  file_path: string;
  line: number | null;
  confidence: number;
  description: string;
  evidence: string;
  recommendation: string;
  validation_status: string;
  suggested_fix?: string;
};

type Analysis = {
  analysis_id: string;
  source: string;
  language: string;
  files_analyzed: number;
  findings: Finding[];
  summary: string;
  ai_analysis_used: boolean;
  warnings: string[];
  repository_url?: string;
};

type FixResult = {
  fixed_code: string;
  explanation: string;
  validation: {
    status: string;
    message: string;
  };
};

const API =
  (import.meta.env.VITE_API_BASE_URL as string | undefined)?.trim() ||
  'http://127.0.0.1:8001';

const sample = `def average(numbers):
    return sum(numbers) / len(numbers)

print(average([]))`;

async function readResponse(res: Response): Promise<any> {
  const responseText = await res.text();

  let data: any;

  try {
    data = responseText ? JSON.parse(responseText) : {};
  } catch {
    throw new Error(
      `Backend returned an invalid response (HTTP ${res.status}).`
    );
  }

  if (!res.ok) {
    const detail = data?.detail;

    throw new Error(
      typeof detail === 'string'
        ? detail
        : Array.isArray(detail)
          ? detail.map((item: any) => item.msg || JSON.stringify(item)).join('; ')
          : `Request failed with HTTP ${res.status}.`
    );
  }

  return data;
}

function getErrorMessage(error: unknown): string {
  if (error instanceof TypeError) {
    return (
      `Could not connect to ${API}. ` +
      'Check that the backend is running on port 8001, ' +
      'verify the frontend API URL, and inspect the browser console for CORS errors.'
    );
  }

  if (error instanceof Error) {
    return error.message;
  }

  return 'An unexpected error occurred. Please try again.';
}

export default function App() {
  const [mode, setMode] = useState<'github' | 'code' | 'upload'>('github');
  const [repo, setRepo] = useState('');
  const [branch, setBranch] = useState('');
  const [code, setCode] = useState(sample);
  const [filename, setFilename] = useState('main.py');
  const [language, setLanguage] = useState('auto');
  const [bug, setBug] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [selected, setSelected] = useState<Finding | null>(null);
  const [filter, setFilter] = useState('All');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [fix, setFix] = useState<FixResult | null>(null);
  const [fixLoading, setFixLoading] = useState(false);

  const counts = useMemo(
    () => ({
      critical:
        analysis?.findings.filter((f) => f.severity === 'Critical').length || 0,
      high:
        analysis?.findings.filter((f) => f.severity === 'High').length || 0,
      medium:
        analysis?.findings.filter((f) => f.severity === 'Medium').length || 0,
    }),
    [analysis]
  );

  const visible = useMemo(
    () =>
      analysis?.findings.filter(
        (f) => filter === 'All' || f.severity === filter
      ) || [],
    [analysis, filter]
  );

  async function run() {
    setLoading(true);
    setError('');
    setAnalysis(null);
    setSelected(null);
    setFix(null);

    try {
      let res: Response;

      if (mode === 'github') {
        if (!repo.trim()) {
          throw new Error('Enter a GitHub repository URL first.');
        }

        res = await fetch(`${API}/api/v1/analyses/github`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            repository_url: repo.trim(),
            branch: branch.trim() || null,
            max_files: 50,
          }),
        });
      } else if (mode === 'code') {
        if (!code.trim()) {
          throw new Error('Paste some source code before starting analysis.');
        }

        res = await fetch(`${API}/api/v1/analyses/code`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            code,
            filename: filename.trim() || 'snippet.py',
            language,
            bug_description: bug,
          }),
        });
      } else {
        if (!file) {
          throw new Error('Choose a source file or ZIP archive first.');
        }

        const fd = new FormData();
        fd.append('file', file);

        res = await fetch(`${API}/api/v1/analyses/upload`, {
          method: 'POST',
          body: fd,
        });
      }

      const data = await readResponse(res);

      if (!Array.isArray(data.findings)) {
        throw new Error(
          'The backend response is missing the findings array. Check the API response format.'
        );
      }

      setAnalysis(data);
      setSelected(data.findings[0] || null);
    } catch (e: unknown) {
      setError(getErrorMessage(e));
    } finally {
      setLoading(false);
    }
  }

  async function generateFix() {
    if (!selected || !analysis) return;

    setFixLoading(true);
    setError('');
    setFix(null);

    try {
      if (mode !== 'code') {
        throw new Error(
          'For this MVP, fix generation is available for pasted code. Select Paste Code and analyze the source first.'
        );
      }

      const res = await fetch(`${API}/api/v1/findings/fix`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          code,
          filename: filename.trim() || 'snippet.py',
          finding: selected,
        }),
      });

      const data = await readResponse(res);

      if (
        typeof data.fixed_code !== 'string' ||
        !data.validation ||
        typeof data.validation.status !== 'string'
      ) {
        throw new Error(
          'The backend returned an unexpected fix response. Check the API response format.'
        );
      }

      setFix(data as FixResult);
    } catch (e: unknown) {
      setError(getErrorMessage(e));
    } finally {
      setFixLoading(false);
    }
  }

  function downloadReport() {
    if (!analysis) return;

    const blob = new Blob([JSON.stringify(analysis, null, 2)], {
      type: 'application/json',
    });

    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');

    a.href = url;
    a.download = 'codeguard-analysis.json';
    a.click();

    URL.revokeObjectURL(url);
  }

  async function copy(text: string) {
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      setError('Clipboard access is unavailable in this browser.');
    }
  }

  function resetReview() {
    setAnalysis(null);
    setSelected(null);
    setFix(null);
    setError('');
    setFilter('All');
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-icon">
            <ShieldCheck size={22} />
          </div>
          <div>
            <strong>
              CodeGuard <span>AI</span>
            </strong>
            <small>INTELLIGENT CODE REVIEW</small>
          </div>
        </div>

        <div className="nav-label">WORKSPACE</div>

        <button
          className="nav-item active"
          onClick={resetReview}
        >
          <Code2 size={17} /> Code analysis
        </button>

        <button
          className="nav-item"
          onClick={resetReview}
        >
          <FileCode2 size={17} /> New review
        </button>

        <div className="sidebar-bottom">
          <div className="secure-card">
            <ShieldCheck size={18} />
            <strong>Security first</strong>
            <p>
              Source code is treated as untrusted input. Never run unknown
              repository code on your host.
            </p>
          </div>
          <div className="version">
            CODEGUARD AI <span>v1.0.0 MVP</span>
          </div>
        </div>
      </aside>

      <main className="main">
        <header className="topbar">
          <div className="breadcrumb">
            Workspace <span>/</span> <b>Code analysis</b>
          </div>
          <div className="top-actions">
            <span className="status-dot" />
            Local analysis API <span className="avatar">CG</span>
          </div>
        </header>

        <div className="content">
          <section className="hero">
            <div>
              <div className="eyebrow">
                <Sparkles size={14} /> AI-ASSISTED CODE INTELLIGENCE
              </div>
              <h1>
                Find bugs before
                <br />
                <span>they find you.</span>
              </h1>
              <p>
                Analyze repositories, inspect code, surface vulnerabilities,
                and generate actionable fixes in one workspace.
              </p>
            </div>

            <div className="hero-art">
              <div className="orbit orbit-one" />
              <div className="orbit orbit-two" />
              <div className="hero-shield">
                <ShieldCheck size={54} />
              </div>
              <div className="floating-tag tag-one">
                <Bug size={14} /> Bug detection
              </div>
              <div className="floating-tag tag-two">
                <CheckCircle2 size={14} /> Fix suggestions
              </div>
            </div>
          </section>

          <section className="workspace-grid">
            <div className="panel input-panel">
              <div className="panel-head">
                <div>
                  <h2>Start a code review</h2>
                  <p>Choose how you want to provide your source.</p>
                </div>
                <span className="step-pill">STEP 01</span>
              </div>

              <div className="tabs">
                <button
                  className={mode === 'github' ? 'selected' : ''}
                  onClick={() => {
                    setMode('github');
                    setError('');
                  }}
                >
                  <Code2 size={16} /> GitHub repo
                </button>

                <button
                  className={mode === 'code' ? 'selected' : ''}
                  onClick={() => {
                    setMode('code');
                    setError('');
                  }}
                >
                  <Code2 size={16} /> Paste code
                </button>

                <button
                  className={mode === 'upload' ? 'selected' : ''}
                  onClick={() => {
                    setMode('upload');
                    setError('');
                  }}
                >
                  <Upload size={16} /> Upload
                </button>
              </div>

              {mode === 'github' && (
                <div className="form-stack">
                  <label htmlFor="repository-url">Repository URL</label>
                  <div className="input-with-icon">
                    <Code2 size={17} />
                    <input
                      id="repository-url"
                      name="repositoryUrl"
                      type="url"
                      value={repo}
                      onChange={(e) => setRepo(e.target.value)}
                      placeholder="https://github.com/owner/repository"
                    />
                  </div>

                  <label htmlFor="branch">
                    Branch <span className="optional">OPTIONAL</span>
                  </label>
                  <input
                    id="branch"
                    name="branch"
                    value={branch}
                    onChange={(e) => setBranch(e.target.value)}
                    placeholder="Default branch if empty"
                  />

                  <div className="hint">
                    <ShieldCheck size={14} />
                    Public repositories work without a token. Private
                    repositories need a configured token.
                  </div>
                </div>
              )}

              {mode === 'code' && (
                <div className="form-stack">
                  <div className="two-fields">
                    <div>
                      <label htmlFor="filename">Filename</label>
                      <input
                        id="filename"
                        name="filename"
                        value={filename}
                        onChange={(e) => setFilename(e.target.value)}
                        placeholder="main.py"
                      />
                    </div>

                    <div>
                      <label htmlFor="language">Language</label>
                      <select
                        id="language"
                        name="language"
                        value={language}
                        onChange={(e) => setLanguage(e.target.value)}
                      >
                        <option value="auto">Auto detect</option>
                        <option value="python">Python</option>
                        <option value="javascript">JavaScript</option>
                        <option value="typescript">TypeScript</option>
                        <option value="java">Java</option>
                      </select>
                    </div>
                  </div>

                  <label htmlFor="source-code">Source code</label>
                  <textarea
                    id="source-code"
                    name="sourceCode"
                    className="code-input"
                    spellCheck={false}
                    value={code}
                    onChange={(e) => setCode(e.target.value)}
                  />

                  <label htmlFor="bug-description">
                    What problem are you seeing?{' '}
                    <span className="optional">OPTIONAL</span>
                  </label>
                  <input
                    id="bug-description"
                    name="bugDescription"
                    value={bug}
                    onChange={(e) => setBug(e.target.value)}
                    placeholder="Describe the bug or expected behavior"
                  />
                </div>
              )}

              {mode === 'upload' && (
                <div className="upload-zone">
                  <Upload size={27} />
                  <strong>Upload source file or ZIP</strong>
                  <p>UTF-8 text files and ZIP archives. Limits apply.</p>
                  <label htmlFor="source-file">Choose source file</label>
                  <input
                    id="source-file"
                    name="sourceFile"
                    type="file"
                    accept=".py,.js,.jsx,.ts,.tsx,.java,.go,.rb,.php,.sql,.zip,.json,.yaml,.yml,.toml"
                    onChange={(e) =>
                      setFile(e.target.files?.[0] || null)
                    }
                  />
                  {file && (
                    <div className="file-selected">
                      <FileCode2 size={15} /> {file.name}
                    </div>
                  )}
                </div>
              )}

              {error && (
                <div className="error-box" role="alert">
                  <AlertTriangle size={16} />
                  <span>{error}</span>
                </div>
              )}

              <button
                className="primary-btn"
                onClick={run}
                disabled={
                  loading ||
                  (mode === 'github' && !repo.trim()) ||
                  (mode === 'code' && !code.trim()) ||
                  (mode === 'upload' && !file)
                }
              >
                {loading ? (
                  <>
                    <LoaderCircle className="spin" size={17} />
                    Analyzing source...
                  </>
                ) : (
                  <>
                    <Search size={17} /> Analyze code <span>→</span>
                  </>
                )}
              </button>

              <div className="privacy-note">
                <ShieldCheck size={13} />
                Review findings before applying any generated fix.
              </div>
            </div>

            <div className="panel overview-panel">
              <div className="panel-head">
                <div>
                  <h2>Analysis overview</h2>
                  <p>
                    {analysis
                      ? 'Latest analysis results'
                      : 'Your findings will appear here'}
                  </p>
                </div>

                <span className="live-pill">
                  <span />
                  {analysis ? 'COMPLETED' : loading ? 'RUNNING' : 'READY'}
                </span>
              </div>

              <div className="metric-grid">
                <div className="metric">
                  <div className="metric-icon red">
                    <AlertTriangle size={17} />
                  </div>
                  <span>Critical</span>
                  <strong>{counts.critical}</strong>
                </div>

                <div className="metric">
                  <div className="metric-icon orange">
                    <Bug size={17} />
                  </div>
                  <span>High severity</span>
                  <strong>{counts.high}</strong>
                </div>

                <div className="metric">
                  <div className="metric-icon yellow">
                    <Search size={17} />
                  </div>
                  <span>Medium</span>
                  <strong>{counts.medium}</strong>
                </div>
              </div>

              <div className="overview-divider" />

              <div className="overview-row">
                <span>Files analyzed</span>
                <strong>{analysis?.files_analyzed ?? '—'}</strong>
              </div>

              <div className="overview-row">
                <span>Primary language</span>
                <strong>{analysis?.language ?? '—'}</strong>
              </div>

              <div className="overview-row">
                <span>AI review</span>
                <strong>
                  {analysis
                    ? analysis.ai_analysis_used
                      ? 'Enabled'
                      : 'Static checks only'
                    : '—'}
                </strong>
              </div>

              {analysis && (
                <>
                  <div className="summary-box">
                    <strong>Review summary</strong>
                    <p>{analysis.summary}</p>
                  </div>

                  {analysis.warnings?.map((w, i) => (
                    <div className="warning-line" key={i}>
                      <AlertTriangle size={14} /> {w}
                    </div>
                  ))}

                  <button
                    className="secondary-btn"
                    onClick={downloadReport}
                  >
                    <Download size={15} /> Export JSON report
                  </button>
                </>
              )}
            </div>
          </section>

          <section className="panel findings-panel">
            <div className="panel-head findings-heading">
              <div>
                <h2>
                  Findings{' '}
                  <span className="count-badge">
                    {analysis?.findings.length ?? 0}
                  </span>
                </h2>
                <p>Prioritized issues detected in the submitted source.</p>
              </div>

              <div className="filter-wrap">
                <label htmlFor="severity-filter">Severity</label>
                <select
                  id="severity-filter"
                  name="severityFilter"
                  value={filter}
                  onChange={(e) => setFilter(e.target.value)}
                >
                  <option>All</option>
                  <option>Critical</option>
                  <option>High</option>
                  <option>Medium</option>
                  <option>Low</option>
                  <option>Info</option>
                </select>
              </div>
            </div>

            {!analysis ? (
              <div className="empty-state">
                <div className="empty-icon">
                  <Bug size={25} />
                </div>
                <strong>No analysis yet</strong>
                <p>
                  Submit a repository or code snippet to see findings,
                  evidence, and fix recommendations.
                </p>
              </div>
            ) : visible.length === 0 ? (
              <div className="empty-state">
                <CheckCircle2 size={25} />
                <strong>No matching findings</strong>
                <p>
                  Try another severity filter. A clean scan does not guarantee
                  bug-free code.
                </p>
              </div>
            ) : (
              <div className="findings-layout">
                <div className="finding-list">
                  {visible.map((f) => (
                    <button
                      key={f.id}
                      className={`finding-item ${
                        selected?.id === f.id ? 'chosen' : ''
                      }`}
                      onClick={() => {
                        setSelected(f);
                        setFix(null);
                      }}
                    >
                      <div className="finding-top">
                        <span
                          className={`severity severity-${f.severity.toLowerCase()}`}
                        >
                          {f.severity}
                        </span>

                        <span className="finding-line">
                          {f.line ? `L${f.line}` : '—'}
                        </span>
                      </div>

                      <strong>{f.title}</strong>

                      <span className="finding-file">
                        <FileCode2 size={13} /> {f.file_path}
                      </span>

                      <p>{f.description}</p>
                    </button>
                  ))}
                </div>

                <div className="finding-detail">
                  {selected ? (
                    <>
                      <div className="detail-title-row">
                        <div>
                          <span
                            className={`severity severity-${selected.severity.toLowerCase()}`}
                          >
                            {selected.severity}
                          </span>
                          <h3>{selected.title}</h3>
                        </div>

                        <button
                          className="icon-btn"
                          title="Copy evidence"
                          aria-label="Copy evidence"
                          onClick={() => copy(selected.evidence)}
                        >
                          <Copy size={15} />
                        </button>
                      </div>

                      <div className="detail-meta">
                        <span>{selected.category}</span>
                        <span>
                          Confidence {Math.round(selected.confidence * 100)}%
                        </span>
                        <span>
                          {selected.file_path}
                          {selected.line ? `:${selected.line}` : ''}
                        </span>
                      </div>

                      <h4>What we found</h4>
                      <p>{selected.description}</p>

                      <h4>Evidence</h4>
                      <pre className="evidence">
                        <code>
                          {selected.evidence || 'No code excerpt supplied.'}
                        </code>
                      </pre>

                      <h4>Recommended action</h4>
                      <p>{selected.recommendation}</p>

                      {selected.suggested_fix && (
                        <>
                          <h4>Suggested fix from review</h4>
                          <pre className="evidence">
                            <code>{selected.suggested_fix}</code>
                          </pre>
                        </>
                      )}

                      <button
                        className="primary-btn fix-btn"
                        onClick={generateFix}
                        disabled={fixLoading}
                      >
                        {fixLoading ? (
                          <>
                            <LoaderCircle size={16} className="spin" />
                            Generating fix...
                          </>
                        ) : (
                          <>
                            <Sparkles size={16} /> Generate corrected code
                          </>
                        )}
                      </button>

                      {fix && (
                        <div className="fix-result">
                          <div className="fix-result-head">
                            <strong>Proposed patch</strong>
                            <span
                              className={`validation ${fix.validation.status}`}
                            >
                              {fix.validation.status.replace('_', ' ')}
                            </span>
                          </div>

                          <p>{fix.explanation}</p>

                          <pre className="evidence">
                            <code>{fix.fixed_code}</code>
                          </pre>

                          <p className="validation-msg">
                            {fix.validation.message}
                          </p>

                          <div className="button-row">
                            <button
                              className="secondary-btn"
                              onClick={() => copy(fix.fixed_code)}
                            >
                              <Copy size={14} /> Copy fixed code
                            </button>

                            <button
                              className="secondary-btn"
                              onClick={() => {
                                const blob = new Blob([fix.fixed_code], {
                                  type: 'text/plain',
                                });

                                const url = URL.createObjectURL(blob);
                                const a = document.createElement('a');

                                a.href = url;
                                a.download = `fixed-${filename || 'snippet.py'}`;
                                a.click();

                                URL.revokeObjectURL(url);
                              }}
                            >
                              <Download size={14} /> Download
                            </button>
                          </div>
                        </div>
                      )}
                    </>
                  ) : (
                    <div className="empty-detail">
                      Select a finding to inspect its evidence and recommended
                      fix.
                    </div>
                  )}
                </div>
              </div>
            )}
          </section>

          <footer>
            <span>CodeGuard AI · Built for safer software</span>
            <span>
              <RefreshCw size={12} /> Static checks + optional AI review
            </span>
          </footer>
        </div>
      </main>
    </div>
  );
}
