import { useState, useEffect, Fragment } from "react";
import { Link } from "react-router-dom";
import { Menu, MenuItem, Divider } from "@mui/material";
import { FileText, Moon, Sun, Download, ChevronDown, ChevronUp } from "lucide-react";
import axios from "axios";

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
  const [isDark, setIsDark] = useState(false);
  const [user, setUser] = useState(null);
  const [userChecked, setUserChecked] = useState(false);
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(null);
  const [anchorEl, setAnchorEl] = useState(null);
  const menuOpen = Boolean(anchorEl);

  const [openDetailFor, setOpenDetailFor] = useState(null);
  const [detailPairs, setDetailPairs] = useState({});
  const [detailLoading, setDetailLoading] = useState(null);
  const [detailError, setDetailError] = useState(null);

  useEffect(() => {
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    setIsDark(mq.matches);
  }, []);

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

  const toggleDetail = async (row) => {
    if (openDetailFor === row.job_id) {
      setOpenDetailFor(null);
      return;
    }
    setOpenDetailFor(row.job_id);
    if (detailPairs[row.job_id]) return;

    setDetailLoading(row.job_id);
    setDetailError(null);
    try {
      const { data } = await axios.get(`/api/results/${row.job_id}/detail`, {
        withCredentials: true,
      });
      setDetailPairs((prev) => ({ ...prev, [row.job_id]: data.pairs || [] }));
    } catch (err) {
      setDetailError(err.response?.data?.error || "Failed to load detail.");
    } finally {
      setDetailLoading(null);
    }
  };

  const header = (
    <header className="sticky top-0 z-20 border-b border-border bg-background/80 backdrop-blur-md">
      <div className="max-w-4xl mx-auto px-5 h-14 flex items-center justify-between">
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
        <main className="max-w-4xl mx-auto px-5 py-16 text-center">
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
      <main className="max-w-4xl mx-auto px-5 py-10 pb-20">
        <div className="mb-8">
          <h1 className="text-2xl font-bold tracking-tight mb-2 text-foreground">
            Your Saved Scorings
          </h1>
          <p className="text-sm text-muted-foreground">
            Every resume + job description pair you've saved, with its score and full breakdown.
          </p>
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

        {!loading && rows.length > 0 && (
          <div className="rounded-xl border border-border overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-muted/40 text-left text-xs uppercase tracking-wide text-muted-foreground">
                  <tr>
                    <th className="px-4 py-3 font-semibold">Resume</th>
                    <th className="px-4 py-3 font-semibold">Job</th>
                    <th className="px-4 py-3 font-semibold">Score</th>
                    <th className="px-4 py-3 font-semibold">Detail</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row) => {
                    const colors = scoreColor(row.overall_score);
                    const isOpen = openDetailFor === row.job_id;
                    return (
                      <Fragment key={row.job_id}>
                        <tr className="border-t border-border">
                          <td className="px-4 py-3">
                            <a
                              href={`/api/resumes/${row.resume_id}/download`}
                              className="flex items-center gap-2 hover:underline"
                              style={{ color: "#aa3bff" }}
                            >
                              <FileText className="w-4 h-4 shrink-0" />
                              <span className="truncate max-w-[180px]">
                                {row.resume_filename || "resume.pdf"}
                              </span>
                            </a>
                          </td>
                          <td className="px-4 py-3">
                            <div className="font-medium">
                              {row.position || "Unknown Position"}
                            </div>
                            <div className="text-muted-foreground text-xs mb-1">
                              {row.company_name || "Unknown Company"}
                            </div>
                            <a
                              href={`/api/jds/${row.jd_id}/download`}
                              className="inline-flex items-center gap-1 text-xs hover:underline"
                              style={{ color: "#aa3bff" }}
                            >
                              <Download className="w-3 h-3" />
                              Download JD
                            </a>
                          </td>
                          <td className="px-4 py-3">
                            <span
                              className={`inline-flex items-center justify-center px-2.5 py-1 rounded-full text-xs font-semibold border ${colors.text} ${colors.bg} ${colors.border}`}
                            >
                              {row.overall_score.toFixed(1)}
                            </span>
                          </td>
                          <td className="px-4 py-3">
                            <button
                              onClick={() => toggleDetail(row)}
                              className="inline-flex items-center gap-1 text-xs font-medium hover:underline"
                              style={{ color: "#aa3bff" }}
                            >
                              {isOpen ? (
                                <ChevronUp className="w-3.5 h-3.5" />
                              ) : (
                                <ChevronDown className="w-3.5 h-3.5" />
                              )}
                              {isOpen ? "Hide" : "View"}
                            </button>
                          </td>
                        </tr>
                        {isOpen && (
                          <tr className="border-t border-border bg-muted/20">
                            <td colSpan={4} className="px-4 py-4">
                              {detailLoading === row.job_id && (
                                <p className="text-xs text-muted-foreground">Loading detail...</p>
                              )}
                              {detailError && detailLoading !== row.job_id && (
                                <p className="text-xs text-red-500">{detailError}</p>
                              )}
                              {detailPairs[row.job_id] && (
                                <>
                                  <button
                                    onClick={() =>
                                      downloadTextBlob(
                                        `${row.job_id}_detail.txt`,
                                        formatDetailAsText(row, detailPairs[row.job_id]),
                                      )
                                    }
                                    className="mb-3 inline-flex items-center gap-1.5 h-8 px-3 rounded-md text-xs font-medium border border-border text-muted-foreground hover:text-foreground hover:border-[#aa3bff]/40 hover:bg-muted/30 transition-all"
                                  >
                                    <Download className="w-3.5 h-3.5" />
                                    Download full detail (.txt)
                                  </button>
                                  <pre className="whitespace-pre-wrap font-mono-data text-xs leading-relaxed text-foreground/90 max-h-80 overflow-y-auto">
                                    {formatDetailAsText(row, detailPairs[row.job_id])}
                                  </pre>
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
      </main>
    </div>
  );
}
