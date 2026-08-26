import { useState, useEffect, Fragment } from "react";
import { Link } from "react-router-dom";
import { Menu, MenuItem, Divider } from "@mui/material";
import {
  FileText,
  Moon,
  Sun,
  Download,
  ChevronDown,
  ChevronUp,
  Trash2,
  Search,
  Link2,
} from "lucide-react";
import axios from "axios";

const RING_RADIUS = 14;
const RING_CIRCUMFERENCE = 2 * Math.PI * RING_RADIUS;

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
    bg: "bg-red-50 dark:bg-red-950/40",
    border: "border-red-200 dark:border-red-800/60",
  };
}

function formatDate(iso) {
  const d = new Date(iso);
  const day = String(d.getDate()).padStart(2, "0");
  const month = d.toLocaleDateString("en-US", { month: "short" });
  return `${day} ${month} ${d.getFullYear()}`;
}

function ScoreRing({ score }) {
  const colors = scoreColor(score);
  const dash = (Math.max(0, Math.min(score, 10)) / 10) * RING_CIRCUMFERENCE;
  return (
    <span className={`inline-flex items-center gap-2 ${colors.text}`}>
      <svg width="28" height="28" viewBox="0 0 36 36" className="shrink-0">
        <circle
          cx="18"
          cy="18"
          r={RING_RADIUS}
          fill="none"
          className="stroke-muted"
          strokeWidth="5"
        />
        <circle
          cx="18"
          cy="18"
          r={RING_RADIUS}
          fill="none"
          stroke="currentColor"
          strokeWidth="5"
          strokeDasharray={`${dash} ${RING_CIRCUMFERENCE}`}
          strokeLinecap="round"
          transform="rotate(-90 18 18)"
        />
      </svg>
      <span className="font-mono-data font-bold text-base leading-none">
        {score.toFixed(1)}
      </span>
    </span>
  );
}

function formatDetailAsText(row, pairs) {
  const lines = [
    `${row.company_name || "Unknown Company"} — ${row.position || "Unknown Position"}`,
    `Overall score: ${row.overall_score.toFixed(1)}`,
    "",
  ];
  const bySection = pairs.reduce((acc, p) => {
    (acc[p.jd_section_name] ??= []).push(p);
    return acc;
  }, {});
  for (const [jdSection, sectionPairs] of Object.entries(bySection)) {
    lines.push(`=== ${jdSection} ===`);
    for (const p of sectionPairs) {
      lines.push(`- ${p.resume_section_name}: ${p.matching_score.toFixed(1)}`);
      lines.push(`  ${p.rationale}`);
    }
    lines.push("");
  }
  return lines.join("\n");
}

function downloadTextBlob(filename, text) {
  const blob = new Blob([text], { type: "text/plain" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export default function Dashboard() {
  const [isDark, setIsDark] = useState(
    () => window.matchMedia("(prefers-color-scheme: dark)").matches,
  );
  const [user, setUser] = useState(null);
  const [userChecked, setUserChecked] = useState(false);
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(null);
  const [anchorEl, setAnchorEl] = useState(null);
  const menuOpen = Boolean(anchorEl);

  const [filterQuery, setFilterQuery] = useState("");

  const [openDetailFor, setOpenDetailFor] = useState(null);
  const [detailPairs, setDetailPairs] = useState({});
  const [detailLoading, setDetailLoading] = useState(null);
  const [detailError, setDetailError] = useState(null);
  const [reportDownloading, setReportDownloading] = useState(null);

  const [resumes, setResumes] = useState([]);
  const [resumesLoading, setResumesLoading] = useState(true);
  const [resumesError, setResumesError] = useState(null);
  const [deletingID, setDeletingID] = useState(null);
  const [deleteError, setDeleteError] = useState(null);

  useEffect(() => {
    document.documentElement.classList.toggle("dark", isDark);
  }, [isDark]);

  useEffect(() => {
    axios
      .get("/api/auth/me", { withCredentials: true })
      .then(({ data }) => setUser(data.user))
      .catch(() => setUser(null))
      .finally(() => setUserChecked(true));
  }, []);

  useEffect(() => {
    if (!userChecked || !user) return;
    axios
      .get("/api/results/mine", { withCredentials: true })
      .then(({ data }) => setRows(data ?? []))
      .catch((err) => setLoadError(err.response?.data?.error || "Failed to load saved results."))
      .finally(() => setLoading(false));
  }, [userChecked, user]);

  useEffect(() => {
    if (!userChecked || !user) return;
    axios
      .get("/api/resumes/mine", { withCredentials: true })
      .then(({ data }) => setResumes(data ?? []))
      .catch((err) => setResumesError(err.response?.data?.error || "Failed to load saved resumes."))
      .finally(() => setResumesLoading(false));
  }, [userChecked, user]);

  const handleLogout = async () => {
    try {
      await axios.post("/api/auth/logout", {}, { withCredentials: true });
    } catch (err) {
      console.error("Logout failed", err);
    } finally {
      setUser(null);
      setAnchorEl(null);
    }
  };

  // Fetches (and caches) the resume-section x JD-section pairs for one saved
  // result. Shared by the inline expand toggle and the "Score report"
  // download button, which both need the same data.
  const fetchDetail = async (row) => {
    if (detailPairs[row.job_id]) return detailPairs[row.job_id];
    setDetailLoading(row.job_id);
    setDetailError(null);
    try {
      const { data } = await axios.get(`/api/results/${row.job_id}/detail`, {
        withCredentials: true,
      });
      const pairs = data.pairs || [];
      setDetailPairs((prev) => ({ ...prev, [row.job_id]: pairs }));
      return pairs;
    } catch (err) {
      setDetailError(err.response?.data?.error || "Failed to load detail.");
      return null;
    } finally {
      setDetailLoading(null);
    }
  };

  const toggleDetail = async (row) => {
    if (openDetailFor === row.job_id) {
      setOpenDetailFor(null);
      return;
    }
    setOpenDetailFor(row.job_id);
    await fetchDetail(row);
  };

  const downloadReport = async (row) => {
    setReportDownloading(row.job_id);
    const pairs = await fetchDetail(row);
    setReportDownloading(null);
    if (pairs) {
      downloadTextBlob(`${row.job_id}_detail.txt`, formatDetailAsText(row, pairs));
    }
  };

  const deleteResume = async (resumeId) => {
    setDeleteError(null);
    setDeletingID(resumeId);
    try {
      await axios.delete(`/api/resumes/${resumeId}`, { withCredentials: true });
      setResumes((prev) => prev.filter((r) => r.resume_id !== resumeId));
    } catch (err) {
      setDeleteError(err.response?.data?.error || "Failed to delete resume.");
    } finally {
      setDeletingID(null);
    }
  };

  const deleteResult = async (jobId) => {
    setDeleteError(null);
    setDeletingID(jobId);
    try {
      await axios.delete(`/api/results/${jobId}`, { withCredentials: true });
      setRows((prev) => prev.filter((r) => r.job_id !== jobId));
      if (openDetailFor === jobId) setOpenDetailFor(null);
    } catch (err) {
      setDeleteError(err.response?.data?.error || "Failed to delete result.");
    } finally {
      setDeletingID(null);
    }
  };

  const filteredRows = rows.filter((row) => {
    const q = filterQuery.trim().toLowerCase();
    if (!q) return true;
    return (
      (row.company_name || "").toLowerCase().includes(q) ||
      (row.position || "").toLowerCase().includes(q)
    );
  });

  const header = (
    <header className="sticky top-0 z-20 border-b border-border bg-background/80 backdrop-blur-md">
      <div className="max-w-6xl mx-auto px-5 h-14 flex items-center justify-between">
        <Link to="/" className="flex items-center gap-2.5">
          <div
            className="w-6 h-6 rounded-md flex items-center justify-center"
            style={{ background: "#aa3bff" }}
          >
            <FileText className="w-3.5 h-3.5 text-white" />
          </div>
          <span className="font-semibold text-sm tracking-tight">PaReJob</span>
        </Link>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setIsDark((d) => !d)}
            className="w-8 h-8 flex items-center justify-center rounded-md text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
            aria-label="Toggle dark mode"
          >
            {isDark ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
          </button>
          {user && (
            <button
              onClick={(e) => setAnchorEl(e.currentTarget)}
              className="flex items-center gap-2 rounded-full hover:opacity-80 transition-opacity"
            >
              <img
                src={user.picture}
                className="w-7 h-7 rounded-full"
                alt={user.name}
                referrerPolicy="no-referrer"
              />
              <span className="text-sm">{user.name}</span>
              <Menu
                anchorEl={anchorEl}
                open={menuOpen}
                onClose={() => setAnchorEl(null)}
                anchorOrigin={{ vertical: "bottom", horizontal: "right" }}
                transformOrigin={{ vertical: "top", horizontal: "right" }}
              >
                <MenuItem component={Link} to="/" onClick={() => setAnchorEl(null)}>
                  Score another resume
                </MenuItem>
                <MenuItem component={Link} to="/profile" onClick={() => setAnchorEl(null)}>
                  Profile
                </MenuItem>
                <Divider />
                <MenuItem onClick={handleLogout}>Logout</MenuItem>
              </Menu>
            </button>
          )}
        </div>
      </div>
    </header>
  );

  if (!userChecked) {
    return (
      <div className="min-h-screen bg-background text-foreground transition-colors duration-200">
        {header}
      </div>
    );
  }

  if (!user) {
    return (
      <div className="min-h-screen bg-background text-foreground transition-colors duration-200">
        {header}
        <main className="max-w-6xl mx-auto px-5 py-16 text-center">
          <p className="text-muted-foreground">
            Log in to see your saved resumes, job descriptions, and results.
          </p>
          <Link
            to="/"
            className="inline-block mt-4 text-sm font-medium"
            style={{ color: "#aa3bff" }}
          >
            Go back and log in
          </Link>
        </main>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background text-foreground transition-colors duration-200">
      {header}

      {deleteError && (
        <div className="max-w-6xl mx-auto px-5 pt-6">
          <div className="p-4 rounded-lg border border-red-200 dark:border-red-800/60 bg-red-50 dark:bg-red-950/40 text-red-700 dark:text-red-400 text-sm flex items-center justify-between gap-3">
            <span>{deleteError}</span>
            <button onClick={() => setDeleteError(null)} className="text-xs underline shrink-0">
              Dismiss
            </button>
          </div>
        </div>
      )}

      <main className="max-w-6xl mx-auto px-5 py-8 pb-20 grid grid-cols-1 md:grid-cols-[260px_1fr] gap-8">
        {/* Left rail -- profile, links, saved resumes */}
        <aside className="space-y-5">
          <div className="flex items-center gap-3">
            <img
              src={user.picture}
              alt={user.name}
              referrerPolicy="no-referrer"
              className="w-14 h-14 rounded-full shrink-0"
            />
            <div className="min-w-0">
              <div className="font-bold text-base leading-tight truncate">{user.name}</div>
              <div className="text-xs text-muted-foreground truncate">{user.email}</div>
            </div>
          </div>

          {(user.linkedin || user.website) && (
            <div className="border-t border-border pt-4 space-y-2.5">
              {user.linkedin && (
                <a
                  href={user.linkedin}
                  target="_blank"
                  rel="noreferrer"
                  className="flex items-center gap-1.5 text-xs hover:underline truncate"
                  style={{ color: "#aa3bff" }}
                >
                  <Link2 className="w-3.5 h-3.5 shrink-0" />
                  <span className="truncate">{user.linkedin}</span>
                </a>
              )}
              {user.website && (
                <a
                  href={user.website}
                  target="_blank"
                  rel="noreferrer"
                  className="flex items-center gap-1.5 text-xs hover:underline truncate"
                  style={{ color: "#aa3bff" }}
                >
                  <Link2 className="w-3.5 h-3.5 shrink-0" />
                  <span className="truncate">{user.website}</span>
                </a>
              )}
            </div>
          )}

          <div className="border-t border-border pt-4">
            <h2 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-2.5">
              Saved Resumes ({resumes.length}/3)
            </h2>
            {resumesLoading && <p className="text-xs text-muted-foreground">Loading...</p>}
            {resumesError && <p className="text-xs text-red-500">{resumesError}</p>}
            {!resumesLoading && !resumesError && resumes.length === 0 && (
              <p className="text-xs text-muted-foreground">No resumes saved yet.</p>
            )}
            {resumes.length > 0 && (
              <ul className="space-y-1.5">
                {resumes.map((r) => (
                  <li key={r.resume_id} className="group flex items-center justify-between gap-2">
                    <a
                      href={`/api/resumes/${r.resume_id}/download`}
                      className="flex items-center gap-1.5 text-xs hover:underline min-w-0"
                      style={{ color: "#aa3bff" }}
                    >
                      <FileText className="w-3.5 h-3.5 shrink-0" />
                      <span className="truncate">{r.filename}</span>
                    </a>
                    <button
                      onClick={() => deleteResume(r.resume_id)}
                      disabled={deletingID === r.resume_id}
                      className="shrink-0 opacity-0 group-hover:opacity-100 text-muted-foreground hover:text-red-500 transition-all disabled:opacity-50"
                      aria-label={`Delete ${r.filename}`}
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div className="border-t border-border pt-4">
            <Link
              to="/profile"
              className="text-xs font-medium hover:underline"
              style={{ color: "#aa3bff" }}
            >
              Edit profile
            </Link>
          </div>
        </aside>

        {/* Main content -- toolbar + saved scorings table */}
        <div className="min-w-0">
          <div className="flex items-center gap-3 mb-5">
            <div className="relative flex-1 max-w-xs">
              <Search className="w-3.5 h-3.5 absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground/60" />
              <input
                type="text"
                value={filterQuery}
                onChange={(e) => setFilterQuery(e.target.value)}
                placeholder="Filter by company or title"
                className="w-full h-9 pl-8 pr-3 rounded-lg border border-border bg-card text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-[#aa3bff]/30 focus:border-[#aa3bff] transition-all placeholder:text-muted-foreground/50"
              />
            </div>
            <span className="text-xs text-muted-foreground shrink-0">
              {rows.length} saved scoring{rows.length === 1 ? "" : "s"}
            </span>
            <Link
              to="/"
              className="ml-auto shrink-0 h-9 px-3.5 flex items-center rounded-lg text-sm font-semibold text-white transition-all"
              style={{ background: "#aa3bff" }}
            >
              Score a resume
            </Link>
          </div>

          {loading && (
            <p className="text-sm text-muted-foreground text-center py-10">Loading...</p>
          )}

          {loadError && (
            <div className="mb-6 p-4 rounded-lg border border-red-200 dark:border-red-800/60 bg-red-50 dark:bg-red-950/40 text-red-700 dark:text-red-400 text-sm">
              {loadError}
            </div>
          )}

          {!loading && !loadError && rows.length === 0 && (
            <p className="text-sm text-muted-foreground text-center py-10">
              Nothing saved yet — score a resume, then click "Save this result" to see it here.
            </p>
          )}

          {!loading && rows.length > 0 && filteredRows.length === 0 && (
            <p className="text-sm text-muted-foreground text-center py-10">
              No saved scorings match "{filterQuery}".
            </p>
          )}

          {!loading && filteredRows.length > 0 && (
            <div className="rounded-xl border border-border overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="bg-muted/40 text-left text-xs uppercase tracking-wide text-muted-foreground">
                    <tr>
                      <th className="px-4 py-3 font-semibold">Job title</th>
                      <th className="px-4 py-3 font-semibold">Company</th>
                      <th className="px-4 py-3 font-semibold">Added</th>
                      <th className="px-4 py-3 font-semibold">Score</th>
                      <th className="px-4 py-3 font-semibold">Downloads</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredRows.map((row) => {
                      const isOpen = openDetailFor === row.job_id;
                      return (
                        <Fragment key={row.job_id}>
                          <tr className="border-t border-border">
                            <td className="px-4 py-3 font-medium">
                              {row.position || "Unknown Position"}
                            </td>
                            <td className="px-4 py-3 text-muted-foreground">
                              {row.company_name || "Unknown Company"}
                            </td>
                            <td className="px-4 py-3 text-muted-foreground whitespace-nowrap">
                              {formatDate(row.created_at)}
                            </td>
                            <td className="px-4 py-3">
                              <ScoreRing score={row.overall_score} />
                            </td>
                            <td className="px-4 py-3">
                              <div className="flex items-center gap-1.5 flex-wrap">
                                <a
                                  href={`/api/resumes/${row.resume_id}/download`}
                                  className="h-7 px-2.5 flex items-center rounded-md text-xs font-medium border border-border text-muted-foreground hover:text-foreground hover:border-[#aa3bff]/40 hover:bg-muted/30 transition-all"
                                >
                                  Resume
                                </a>
                                <a
                                  href={`/api/jds/${row.jd_id}/download`}
                                  className="h-7 px-2.5 flex items-center rounded-md text-xs font-medium border border-border text-muted-foreground hover:text-foreground hover:border-[#aa3bff]/40 hover:bg-muted/30 transition-all"
                                >
                                  Job description
                                </a>
                                <button
                                  onClick={() => downloadReport(row)}
                                  disabled={reportDownloading === row.job_id}
                                  className="h-7 px-2.5 flex items-center rounded-md text-xs font-medium border border-border text-muted-foreground hover:text-foreground hover:border-[#aa3bff]/40 hover:bg-muted/30 transition-all disabled:opacity-50"
                                >
                                  {reportDownloading === row.job_id ? "..." : "Score report"}
                                </button>
                                <button
                                  onClick={() => toggleDetail(row)}
                                  className="h-7 w-7 flex items-center justify-center rounded-md text-muted-foreground hover:text-foreground hover:bg-muted/30 transition-all shrink-0"
                                  aria-label={isOpen ? "Hide breakdown" : "View breakdown"}
                                >
                                  {isOpen ? (
                                    <ChevronUp className="w-3.5 h-3.5" />
                                  ) : (
                                    <ChevronDown className="w-3.5 h-3.5" />
                                  )}
                                </button>
                                <button
                                  onClick={() => deleteResult(row.job_id)}
                                  disabled={deletingID === row.job_id}
                                  className="h-7 w-7 flex items-center justify-center rounded-md text-muted-foreground hover:text-red-500 transition-all disabled:opacity-50 shrink-0"
                                  aria-label="Delete result"
                                >
                                  <Trash2 className="w-3.5 h-3.5" />
                                </button>
                              </div>
                            </td>
                          </tr>
                          {isOpen && (
                            <tr className="border-t border-border bg-muted/20">
                              <td colSpan={5} className="px-4 py-4">
                                {detailLoading === row.job_id && (
                                  <p className="text-xs text-muted-foreground">Loading detail...</p>
                                )}
                                {detailError && detailLoading !== row.job_id && (
                                  <p className="text-xs text-red-500">{detailError}</p>
                                )}
                                {detailPairs[row.job_id] && (
                                  <>
                                    <button
                                      onClick={() => downloadReport(row)}
                                      className="mb-3 inline-flex items-center gap-1.5 h-8 px-3 rounded-md text-xs font-medium border border-border text-muted-foreground hover:text-foreground hover:border-[#aa3bff]/40 hover:bg-muted/30 transition-all"
                                    >
                                      <Download className="w-3.5 h-3.5" />
                                      Download full breakdown (.txt)
                                    </button>
                                    <div className="space-y-2">
                                      {detailPairs[row.job_id].map((pair, i) => {
                                        const c = scoreColor(pair.matching_score);
                                        return (
                                          <div
                                            key={i}
                                            className="flex items-start gap-3 rounded-lg border border-border bg-card px-3.5 py-3"
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
                                  </>
                                )}
                              </td>
                            </tr>
                          )}
                        </Fragment>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
