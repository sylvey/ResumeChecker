import { useState, useEffect, useRef } from "react";
import "./App.css";
import {
  Container,
  Paper,
  Stack,
  Box,
  Typography,
  TextField,
  Button,
  Chip,
  LinearProgress,
  Alert,
  Divider,
  CircularProgress,
} from "@mui/material";
import axios from "axios";

const POLL_INTERVAL_MS = 2000;

function scoreColor(score) {
  if (score >= 7) return "success";
  if (score >= 4) return "warning";
  return "error";
}

function App() {
  const [resume, setResume] = useState(null);
  const [jd, setJd] = useState("");
  const [status, setStatus] = useState(null); // null | "running" | "done" | "error"
  const [stage, setStage] = useState("");
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const pollRef = useRef(null);

  // Stop polling if the component unmounts mid-job.
  useEffect(() => {
    return () => clearInterval(pollRef.current);
  }, []);

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

  const onSubmit = async (e) => {
    e.preventDefault();
    if (!resume) {
      alert("Please upload your resume.");
      return;
    }
    if (!jd.trim()) {
      alert("Please enter the job description.");
      return;
    }

    const formData = new FormData();
    formData.append("resume_file", resume);
    formData.append("job_description", jd);

    setStatus("running");
    setStage("Starting...");
    setResult(null);
    setError(null);

    try {
      const res = await axios.post("/api/parse", formData);
      const jobId = res.data.job_id;
      if (!jobId) {
        throw new Error("No job_id returned from server.");
      }
      pollStatus(jobId);
    } catch (err) {
      console.error("Error uploading data:", err);
      setStatus("error");
      setError(err.message);
    }
  };

  const isRunning = status === "running";

  return (
    <Container maxWidth="sm" sx={{ textAlign: "left", py: 6 }}>
      <Stack spacing={0.5} sx={{ mb: 4 }}>
        <Typography variant="h4" sx={{ color: "var(--text-h)", fontWeight: 600 }}>
          ResumeChecker
        </Typography>
        <Typography variant="body2" sx={{ color: "var(--text)" }}>
          Upload a resume and a job description to see how well they match.
        </Typography>
      </Stack>

      <Paper variant="outlined" sx={{ p: 4, borderRadius: 3 }}>
        <Stack spacing={3}>
          <Box>
            <Typography variant="subtitle2" sx={{ mb: 1, color: "var(--text-h)" }}>
              Resume
            </Typography>
            {resume ? (
              <Chip
                label={`${resume.name} · ${(resume.size / 1024).toFixed(1)} KB`}
                onDelete={isRunning ? undefined : () => setResume(null)}
                disabled={isRunning}
                sx={{ maxWidth: "100%" }}
              />
            ) : (
              <Button variant="outlined" component="label" disabled={isRunning}>
                Choose PDF
                <input
                  type="file"
                  accept=".pdf"
                  hidden
                  onChange={(e) => setResume(e.target.files[0])}
                />
              </Button>
            )}
          </Box>

          <TextField
            label="Job Description"
            placeholder="Paste the job description here..."
            multiline
            minRows={6}
            fullWidth
            value={jd}
            disabled={isRunning}
            onChange={(e) => setJd(e.target.value)}
          />

          <Button
            variant="contained"
            size="large"
            disabled={isRunning}
            onClick={onSubmit}
            startIcon={isRunning ? <CircularProgress size={16} color="inherit" /> : null}
            sx={{
              background: "var(--accent)",
              "&:hover": { background: "var(--accent)", opacity: 0.9 },
            }}
          >
            {isRunning ? "Scoring..." : "Check Match"}
          </Button>

          {isRunning && (
            <Box>
              <LinearProgress />
              <Typography variant="body2" sx={{ mt: 1, color: "var(--text)" }}>
                {stage || "Working..."}
              </Typography>
            </Box>
          )}

          {status === "error" && <Alert severity="error">{error}</Alert>}
        </Stack>
      </Paper>

      {status === "done" && result && (
        <Paper variant="outlined" sx={{ p: 4, borderRadius: 3, mt: 3 }}>
          <Stack spacing={2}>
            <Stack direction="row" alignItems="baseline" spacing={1.5}>
              <Typography
                variant="h3"
                sx={{ fontWeight: 700, color: `${scoreColor(result.overall_score)}.main` }}
              >
                {result.overall_score.toFixed(1)}
              </Typography>
              <Typography variant="body2" sx={{ color: "var(--text)" }}>
                / 10 overall match
              </Typography>
            </Stack>

            {result.reply && (
              <Typography variant="body2" sx={{ color: "var(--text)" }}>
                {result.reply}
              </Typography>
            )}

            <Divider />

            <Stack spacing={1.5}>
              {result.pairs?.map((pair, i) => (
                <Box
                  key={i}
                  sx={{
                    border: "1px solid var(--border)",
                    borderRadius: 2,
                    p: 2,
                  }}
                >
                  <Stack
                    direction="row"
                    justifyContent="space-between"
                    alignItems="center"
                    spacing={2}
                  >
                    <Typography variant="subtitle2" sx={{ color: "var(--text-h)" }}>
                      {pair.resume_section_name} × {pair.jd_section_name}
                    </Typography>
                    <Chip
                      label={pair.matching_score}
                      color={scoreColor(pair.matching_score)}
                      size="small"
                    />
                  </Stack>
                  <Typography variant="body2" sx={{ mt: 0.5, color: "var(--text)" }}>
                    {pair.rationale}
                  </Typography>
                </Box>
              ))}
            </Stack>
          </Stack>
        </Paper>
      )}
    </Container>
  );
}

export default App;