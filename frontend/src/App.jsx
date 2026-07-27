import { useState, useEffect, useRef, useCallback } from "react";
import {
  Upload,
  X,
  Moon,
  Sun,
  AlertCircle,
  FileText,
  RotateCcw,
} from "lucide-react";
import axios from "axios";
import ReactMarkdown from "react-markdown";

const POLL_INTERVAL_MS = 2000;

function scoreColor(score) {
  if (score >= 7)
    return {
      text: "text-emerald-600 dark:text-emerald-400",
      bg: "bg-emerald-50 dark:bg-emerald-950/50",
      border: "border-emerald-200 dark:border-emerald-800/60",
    };
  if (score >= 4)
    return {
      text: "text-amber-600 dark:text-amber-400",
      bg: "bg-amber-50 dark:bg-amber-950/50",
      border: "border-amber-200 dark:border-amber-800/60",
    };
  return {
    text: "text-red-600 dark:text-red-400",
    bg: "bg-red-50 dark:bg-red-950/50",
    border: "border-red-200 dark:border-red-800/60",
  };
}

function formatFileSize(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default function App() {
  const [isDark, setIsDark] = useState(false);
  const [resumeFile, setResumeFile] = useState(null);
  const [jdText, setJdText] = useState("");
  const [isDragging, setIsDragging] = useState(false);
  const [status, setStatus] = useState(null); // null | "running" | "done" | "error"
  const [stage, setStage] = useState("");
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  const fileInputRef = useRef(null);
  const pollRef = useRef(null);

  useEffect(() => {
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    setIsDark(mq.matches);
  }, []);

  useEffect(() => {
    document.documentElement.classList.toggle("dark", isDark);
  }, [isDark]);

  useEffect(() => {
    return () => clearInterval(pollRef.current);
  }, []);

  const handleFileSelect = useCallback((file) => {
    if (file.type === "application/pdf" || file.name.endsWith(".pdf")) {
      setResumeFile(file);
    }
  }, []);

  const handleDrop = useCallback(
    (e) => {
      e.preventDefault();
      setIsDragging(false);
      const file = e.dataTransfer.files[0];
      if (file) handleFileSelect(file);
    },
    [handleFileSelect],
  );

  const pollStatus = (jobId) => {
    pollRef.current = setInterval(async () => {
      try {
        const res = await axios.get(`/api/parse/${jobId}/status`);
        const job = res.data;
        setStage(job.stage || "");

        if (job.status === "done") {
          clearInterval(pollRef.current);
          setStatus("done");
          setResult(job);
        } else if (job.status === "error") {
          clearInterval(pollRef.current);
          setStatus("error");
          setError(job.error || "Scoring failed.");
        }
      } catch (err) {
        clearInterval(pollRef.current);
        setStatus("error");
        setError(err.message);
      }
    }, POLL_INTERVAL_MS);
  };

  const onSubmit = async () => {
    if (!resumeFile || !jdText.trim()) return;

    const formData = new FormData();
    formData.append("resume_file", resumeFile);
    formData.append("job_description", jdText);

    setStatus("running");
    setStage("Starting...");
    setResult(null);
    setError(null);

    try {
      const res = await axios.post("/api/parse", formData);
      const jobId = res.data.job_id;
      if (!jobId) throw new Error("No job_id returned from server.");
      pollStatus(jobId);
    } catch (err) {
      setStatus("error");
      setError(err.message);
    }
  };

  const handleReset = () => {
    clearInterval(pollRef.current);
    setStatus(null);
    setStage("");
    setResult(null);
    setError(null);
  };

  const isRunning = status === "running";
  const canSubmit = resumeFile !== null && jdText.trim().length > 0;
  const overallColors = result ? scoreColor(result.overall_score) : null;

  const groupedPairs =
    result?.pairs?.reduce((acc, pair) => {
      const section = pair.resume_section_name;
      if (!acc[section]) acc[section] = [];
      acc[section].push(pair);
      return acc;
    }, {}) ?? {};

  return (
    <>
      <style>{`
        @keyframes indeterminate {
          0%   { transform: translateX(-100%) scaleX(0.5); }
          50%  { transform: translateX(50%) scaleX(0.8); }
          100% { transform: translateX(300%) scaleX(0.5); }
        }
        .indeterminate-bar { animation: indeterminate 1.6s ease-in-out infinite; }
        body { font-family: 'Plus Jakarta Sans', system-ui, sans-serif; }
        .font-mono-data { font-family: 'JetBrains Mono', monospace; }
        ::-webkit-scrollbar { width: 5px; height: 5px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb { background: rgba(128,128,128,0.25); border-radius: 9999px; }
      `}</style>

      <div className="min-h-screen bg-background text-foreground transition-colors duration-200">
        {/* Header */}
        <header className="sticky top-0 z-20 border-b border-border bg-background/80 backdrop-blur-md">
          <div className="max-w-2xl mx-auto px-5 h-14 flex items-center justify-between">
            <div className="flex items-center gap-2.5">
              <div
                className="w-6 h-6 rounded-md flex items-center justify-center"
                style={{ background: "#aa3bff" }}
              >
                <FileText className="w-3.5 h-3.5 text-white" />
              </div>
              <span className="font-semibold text-sm tracking-tight">
                PaReJob
              </span>
            </div>
            <button
              onClick={() => setIsDark((d) => !d)}
              className="w-8 h-8 flex items-center justify-center rounded-md text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
              aria-label="Toggle dark mode"
            >
              {isDark ? (
                <Sun className="w-4 h-4" />
              ) : (
                <Moon className="w-4 h-4" />
              )}
            </button>
          </div>
        </header>

        <main className="max-w-2xl mx-auto px-5 py-10 pb-20">
          {/* Page headline */}
          <div className="mb-9 text-center">
            <h1 className="text-2xl font-bold tracking-tight mb-2 text-foreground">
              Resume Match Score
            </h1>
            <p className="text-sm text-muted-foreground max-w-sm mx-auto leading-relaxed">
              Upload your resume and paste a job description — we score how well
              they align, section by section.
            </p>
          </div>

          {/* Error banner */}
          {status === "error" && error && (
            <div className="mb-6 flex items-start gap-3 p-4 rounded-lg border border-red-200 dark:border-red-800/60 bg-red-50 dark:bg-red-950/40 text-red-700 dark:text-red-400">
              <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
              <span className="flex-1 text-sm leading-relaxed">{error}</span>
              <button
                onClick={() => setError(null)}
                className="shrink-0 text-red-400 hover:text-red-600 dark:hover:text-red-300 transition-colors"
                aria-label="Dismiss error"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
          )}

          {/* Input form — hidden once results are ready */}
          {status !== "done" && (
            <div className="space-y-5">
              {/* Resume upload */}
              <div>
                <label className="block text-sm font-semibold mb-2 text-foreground">
                  Resume
                  <span className="ml-1.5 text-xs font-normal text-muted-foreground">
                    PDF only
                  </span>
                </label>

                {resumeFile ? (
                  <div className="flex items-center gap-3 px-3 py-2.5 rounded-lg border border-border bg-card text-sm">
                    <div
                      className="w-7 h-7 rounded-md flex items-center justify-center shrink-0"
                      style={{ background: "#aa3bff1a" }}
                    >
                      <FileText
                        className="w-3.5 h-3.5"
                        style={{ color: "#aa3bff" }}
                      />
                    </div>
                    <span className="flex-1 truncate font-medium text-sm">
                      {resumeFile.name}
                    </span>
                    <span className="text-xs text-muted-foreground shrink-0">
                      {formatFileSize(resumeFile.size)}
                    </span>
                    <button
                      onClick={() => setResumeFile(null)}
                      disabled={isRunning}
                      className="shrink-0 text-muted-foreground hover:text-foreground transition-colors disabled:opacity-40 disabled:cursor-not-allowed ml-1"
                      aria-label="Remove file"
                    >
                      <X className="w-3.5 h-3.5" />
                    </button>
                  </div>
                ) : (
                  <div
                    onDragOver={(e) => {
                      e.preventDefault();
                      setIsDragging(true);
                    }}
                    onDragLeave={() => setIsDragging(false)}
                    onDrop={handleDrop}
                    onClick={() => fileInputRef.current?.click()}
                    role="button"
                    tabIndex={0}
                    onKeyDown={(e) =>
                      e.key === "Enter" && fileInputRef.current?.click()
                    }
                    className={`flex flex-col items-center justify-center gap-2 px-6 py-9 rounded-lg border-2 border-dashed cursor-pointer transition-all duration-150 select-none ${
                      isDragging
                        ? "border-[#aa3bff] bg-[#aa3bff]/6"
                        : "border-border hover:border-[#aa3bff]/50 hover:bg-muted/40"
                    }`}
                  >
                    <div
                      className="w-9 h-9 rounded-lg flex items-center justify-center"
                      style={{
                        background: isDragging
                          ? "#aa3bff22"
                          : "rgba(128,128,128,0.08)",
                      }}
                    >
                      <Upload
                        className="w-4 h-4 transition-colors"
                        style={{ color: isDragging ? "#aa3bff" : undefined }}
                      />
                    </div>
                    <p className="text-sm font-medium">
                      Drop your resume here,{" "}
                      <span style={{ color: "#aa3bff" }}>or browse</span>
                    </p>
                    <input
                      ref={fileInputRef}
                      type="file"
                      accept=".pdf,application/pdf"
                      className="hidden"
                      onChange={(e) => {
                        const file = e.target.files?.[0];
                        if (file) handleFileSelect(file);
                        e.target.value = "";
                      }}
                    />
                  </div>
                )}
              </div>

              {/* JD textarea */}
              <div>
                <label className="block text-sm font-semibold mb-2 text-foreground">
                  Job Description
                </label>
                <textarea
                  value={jdText}
                  onChange={(e) => setJdText(e.target.value)}
                  placeholder="Paste the job description here..."
                  disabled={isRunning}
                  rows={9}
                  className="w-full px-3.5 py-3 rounded-lg border border-border bg-card text-foreground text-sm resize-none focus:outline-none focus:ring-2 focus:ring-[#aa3bff]/30 focus:border-[#aa3bff] transition-all placeholder:text-muted-foreground/50 disabled:opacity-50 disabled:cursor-not-allowed leading-relaxed"
                />
              </div>

              {/* Submit button */}
              <button
                onClick={onSubmit}
                disabled={!canSubmit || isRunning}
                className="w-full h-11 flex items-center justify-center gap-2 rounded-lg text-sm font-semibold text-white transition-all disabled:opacity-40 disabled:cursor-not-allowed"
                style={{ background: "#aa3bff" }}
                onMouseEnter={(e) => {
                  if (canSubmit && !isRunning)
                    e.currentTarget.style.background = "#9a28f0";
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.background = "#aa3bff";
                }}
              >
                {isRunning ? (
                  <>
                    <svg
                      className="w-4 h-4 animate-spin shrink-0"
                      viewBox="0 0 24 24"
                      fill="none"
                    >
                      <circle
                        className="opacity-25"
                        cx="12"
                        cy="12"
                        r="10"
                        stroke="currentColor"
                        strokeWidth="3.5"
                      />
                      <path
                        className="opacity-80"
                        fill="currentColor"
                        d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
                      />
                    </svg>
                    Scoring...
                  </>
                ) : (
                  "Check Match"
                )}
              </button>

              {/* Loading progress */}
              {isRunning && (
                <div className="pt-1 space-y-3">
                  <div className="w-full h-0.5 rounded-full bg-muted overflow-hidden">
                    <div
                      className="h-full rounded-full indeterminate-bar"
                      style={{ background: "#aa3bff", width: "40%" }}
                    />
                  </div>
                  <div className="text-center space-y-1">
                    <p className="text-sm text-muted-foreground">
                      {stage || "Working..."}
                    </p>
                    <p className="text-xs text-muted-foreground/50">
                      This may take 30 seconds to a couple of minutes
                    </p>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Results */}
          {status === "done" && result && (
            <div className="space-y-5">
              {/* Overall score hero */}
              <div
                className={`rounded-xl border px-6 py-8 text-center ${overallColors.border} ${overallColors.bg}`}
              >
                <div
                  className={`font-mono-data text-6xl font-bold tracking-tight leading-none ${overallColors.text}`}
                >
                  {result.overall_score.toFixed(1)}
                  <span className="text-2xl font-normal text-muted-foreground">
                    {" "}
                    / 10
                  </span>
                </div>
                <p className="text-xs uppercase tracking-widest font-semibold text-muted-foreground mt-3">
                  Overall Match Score
                </p>
              </div>

              {/* AI Summary */}
              {result.reply && (
                <div className="rounded-lg border border-border bg-card px-4 py-4">
                  <p className="text-[11px] font-semibold uppercase tracking-widest text-muted-foreground mb-2">
                    Summary
                  </p>
                  <div className="text-sm leading-relaxed text-foreground [&_p]:mb-2 [&_ul]:pl-4 [&_li]:mb-1 [&_strong]:font-semibold">
                    <ReactMarkdown>{result.reply}</ReactMarkdown>
                  </div>
                </div>
              )}

              {/* Section breakdown */}
              {result.pairs?.length > 0 && (
                <div>
                  <p className="text-[11px] font-semibold uppercase tracking-widest text-muted-foreground mb-3">
                    Section Breakdown
                  </p>
                  <div className="space-y-4">
                    {Object.entries(groupedPairs).map(([section, pairs]) => (
                      <div key={section}>
                        <p className="text-xs font-semibold text-foreground/70 mb-1.5 px-0.5">
                          {section}
                        </p>
                        <div className="space-y-1.5">
                          {pairs.map((pair, i) => {
                            const c = scoreColor(pair.matching_score);
                            return (
                              <div
                                key={i}
                                className="flex items-start gap-3 rounded-lg border border-border bg-card px-3.5 py-3 hover:border-[#aa3bff]/30 transition-colors"
                              >
                                <div
                                  className={`shrink-0 font-mono-data text-xs font-bold px-2 py-0.5 rounded border mt-0.5 ${c.text} ${c.bg} ${c.border}`}
                                >
                                  {pair.matching_score.toFixed(1)}
                                </div>
                                <div className="flex-1 min-w-0">
                                  <p className="text-xs font-medium text-foreground mb-0.5">
                                    <span>{pair.resume_section_name}</span>
                                    <span className="text-muted-foreground mx-1.5">
                                      ×
                                    </span>
                                    <span className="text-muted-foreground">
                                      {pair.jd_section_name}
                                    </span>
                                  </p>
                                  <p className="text-xs text-muted-foreground leading-relaxed">
                                    {pair.rationale}
                                  </p>
                                </div>
                              </div>
                            );
                          })}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Score another */}
              <button
                onClick={handleReset}
                className="w-full h-10 flex items-center justify-center gap-2 rounded-lg text-sm font-medium border border-border text-muted-foreground hover:text-foreground hover:border-[#aa3bff]/40 hover:bg-muted/30 transition-all"
              >
                <RotateCcw className="w-3.5 h-3.5" />
                Score another resume
              </button>
            </div>
          )}
        </main>
      </div>
    </>
  );
}
