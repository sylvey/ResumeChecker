import { useState, useEffect, useRef, useCallback } from "react";
import { FileText, Trash2, Upload } from "lucide-react";
import axios from "axios";

const MAX_SAVED_RESUMES = 3;

// Self-contained "Saved Resumes" panel -- list, upload, delete. Used on both
// the Profile and Dashboard pages so that logic isn't duplicated between
// them; fetches and manages its own state independent of the host page.
export default function SavedResumes() {
  const [resumes, setResumes] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [deletingID, setDeletingID] = useState(null);
  const [deleteError, setDeleteError] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState(null);
  const fileInputRef = useRef(null);

  const fetchResumes = useCallback(() => {
    return axios
      .get("/api/resumes/mine", { withCredentials: true })
      .then(({ data }) => {
        setResumes(data ?? []);
        setError(null);
      })
      .catch((err) => setError(err.response?.data?.error || "Failed to load saved resumes."))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    fetchResumes();
  }, [fetchResumes]);

  const deleteResume = async (resumeId) => {
    const confirmed = window.confirm(
      "If this resume backs a saved result, that result's download will be converted to a text file instead of the PDF. Delete anyway?",
    );
    if (!confirmed) return;

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

  const uploadResume = async (file) => {
    setUploadError(null);
    setUploading(true);
    try {
      const fd = new FormData();
      fd.append("resume_file", file);
      await axios.post("/api/resumes/save", fd, { withCredentials: true });
      await fetchResumes();
    } catch (err) {
      setUploadError(err.response?.data?.error || "Failed to upload resume.");
    } finally {
      setUploading(false);
    }
  };

  const atCap = resumes.length >= MAX_SAVED_RESUMES;

  return (
    <div>
      <h2 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-2.5">
        Saved Resumes ({resumes.length}/{MAX_SAVED_RESUMES})
      </h2>

      {loading && <p className="text-xs text-muted-foreground">Loading...</p>}
      {error && <p className="text-xs text-red-500">{error}</p>}
      {!loading && !error && resumes.length === 0 && (
        <p className="text-xs text-muted-foreground mb-2">No resumes saved yet.</p>
      )}
      {resumes.length > 0 && (
        <ul className="space-y-1.5 mb-2">
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
                className="shrink-0 opacity-100 md:opacity-0 md:group-hover:opacity-100 text-muted-foreground hover:text-red-500 transition-all disabled:opacity-50"
                aria-label={`Delete ${r.filename}`}
              >
                <Trash2 className="w-3.5 h-3.5" />
              </button>
            </li>
          ))}
        </ul>
      )}

      {deleteError && <p className="text-xs text-red-500 mb-2">{deleteError}</p>}
      {uploadError && <p className="text-xs text-red-500 mb-2">{uploadError}</p>}

      {atCap ? (
        <p className="text-xs text-muted-foreground">Resume limit reached (3/3).</p>
      ) : (
        <>
          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf,application/pdf"
            className="hidden"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) uploadResume(file);
              e.target.value = "";
            }}
          />
          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={uploading}
            className="flex items-center gap-1.5 text-xs font-medium hover:underline disabled:opacity-50"
            style={{ color: "#aa3bff" }}
          >
            <Upload className="w-3.5 h-3.5" />
            {uploading ? "Uploading..." : "Upload Resume"}
          </button>
        </>
      )}
    </div>
  );
}
