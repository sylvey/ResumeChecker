import { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import { ArrowLeft, Moon, Sun, Pencil, Link2 } from "lucide-react";
import axios from "axios";

export default function Profile() {
  const [isDark, setIsDark] = useState(
    () => window.matchMedia("(prefers-color-scheme: dark)").matches,
  );
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(false);
  const [bio, setBio] = useState("");
  const [linkedin, setLinkedin] = useState("");
  const [website, setWebsite] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    document.documentElement.classList.toggle("dark", isDark);
  }, [isDark]);

  useEffect(() => {
    axios
      .get("/api/auth/me", { withCredentials: true })
      .then(({ data }) => {
        setUser(data.user);
        setBio(data.user.bio || "");
        setLinkedin(data.user.linkedin || "");
        setWebsite(data.user.website || "");
      })
      .catch(() => setUser(null))
      .finally(() => setLoading(false));
  }, []);

  const startEditing = () => {
    setBio(user.bio || "");
    setLinkedin(user.linkedin || "");
    setWebsite(user.website || "");
    setError(null);
    setEditing(true);
  };

  const cancelEditing = () => {
    setError(null);
    setEditing(false);
  };

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    try {
      const { data } = await axios.patch(
        "/api/auth/me",
        { bio, linkedin, website },
        { withCredentials: true },
      );
      setUser(data.user);
      setEditing(false);
    } catch (err) {
      setError(err.response?.data?.error || err.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="min-h-screen bg-background text-foreground transition-colors duration-200">
      <header className="sticky top-0 z-20 border-b border-border bg-background/80 backdrop-blur-md">
        <div className="max-w-2xl mx-auto px-5 h-14 flex items-center justify-between">
          <Link
            to="/"
            className="flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground transition-colors"
          >
            <ArrowLeft className="w-4 h-4" />
            Back
          </Link>
          <button
            onClick={() => setIsDark((d) => !d)}
            className="w-8 h-8 flex items-center justify-center rounded-md text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
            aria-label="Toggle dark mode"
          >
            {isDark ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
          </button>
        </div>
      </header>

      <main className="max-w-2xl mx-auto px-5 py-10 pb-20">
        {loading ? (
          <p className="text-sm text-muted-foreground text-center">Loading...</p>
        ) : !user ? (
          <div className="text-center space-y-3">
            <p className="text-sm text-muted-foreground">
              You need to be logged in to view your profile.
            </p>
            <Link
              to="/"
              className="inline-flex items-center gap-1.5 text-sm font-medium"
              style={{ color: "#aa3bff" }}
            >
              Go to homepage
            </Link>
          </div>
        ) : (
          <div className="space-y-6">
            <div className="flex items-center justify-between gap-4">
              <div className="flex items-center gap-4">
                <img
                  src={user.picture}
                  alt={user.name}
                  referrerPolicy="no-referrer"
                  className="w-16 h-16 rounded-full"
                />
                <div>
                  <h1 className="text-lg font-bold tracking-tight">{user.name}</h1>
                  <p className="text-sm text-muted-foreground">{user.email}</p>
                </div>
              </div>
              {!editing && (
                <button
                  onClick={startEditing}
                  className="shrink-0 h-9 px-3.5 flex items-center gap-1.5 rounded-lg text-sm font-medium border border-border text-muted-foreground hover:text-foreground hover:border-[#aa3bff]/40 hover:bg-muted/30 transition-all"
                >
                  <Pencil className="w-3.5 h-3.5" />
                  Edit Profile
                </button>
              )}
            </div>

            {error && (
              <div className="text-sm text-red-600 dark:text-red-400">{error}</div>
            )}

            {editing ? (
              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-semibold mb-2 text-foreground">
                    Bio
                  </label>
                  <textarea
                    value={bio}
                    onChange={(e) => setBio(e.target.value)}
                    placeholder="A short bio about yourself..."
                    rows={4}
                    className="w-full px-3.5 py-3 rounded-lg border border-border bg-card text-foreground text-sm resize-none focus:outline-none focus:ring-2 focus:ring-[#aa3bff]/30 focus:border-[#aa3bff] transition-all placeholder:text-muted-foreground/50 leading-relaxed"
                  />
                </div>

                <div>
                  <label className="block text-sm font-semibold mb-2 text-foreground">
                    LinkedIn
                  </label>
                  <input
                    type="url"
                    value={linkedin}
                    onChange={(e) => setLinkedin(e.target.value)}
                    placeholder="https://linkedin.com/in/..."
                    className="w-full px-3.5 py-2.5 rounded-lg border border-border bg-card text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-[#aa3bff]/30 focus:border-[#aa3bff] transition-all placeholder:text-muted-foreground/50"
                  />
                </div>

                <div>
                  <label className="block text-sm font-semibold mb-2 text-foreground">
                    Website
                  </label>
                  <input
                    type="url"
                    value={website}
                    onChange={(e) => setWebsite(e.target.value)}
                    placeholder="https://..."
                    className="w-full px-3.5 py-2.5 rounded-lg border border-border bg-card text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-[#aa3bff]/30 focus:border-[#aa3bff] transition-all placeholder:text-muted-foreground/50"
                  />
                </div>

                <div className="flex gap-3">
                  <button
                    onClick={handleSave}
                    disabled={saving}
                    className="flex-1 h-11 flex items-center justify-center gap-2 rounded-lg text-sm font-semibold text-white transition-all disabled:opacity-60 disabled:cursor-not-allowed"
                    style={{ background: "#aa3bff" }}
                  >
                    {saving ? "Saving..." : "Save Profile"}
                  </button>
                  <button
                    onClick={cancelEditing}
                    disabled={saving}
                    className="h-11 px-5 flex items-center justify-center rounded-lg text-sm font-medium border border-border text-muted-foreground hover:text-foreground hover:bg-muted/30 transition-all disabled:opacity-60 disabled:cursor-not-allowed"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            ) : (
              <div className="space-y-4">
                <div>
                  <p className="text-[11px] font-semibold uppercase tracking-widest text-muted-foreground mb-1.5">
                    Bio
                  </p>
                  <p className="text-sm text-foreground leading-relaxed whitespace-pre-wrap">
                    {user.bio || (
                      <span className="text-muted-foreground/60 italic">
                        No bio yet.
                      </span>
                    )}
                  </p>
                </div>

                <div>
                  <p className="text-[11px] font-semibold uppercase tracking-widest text-muted-foreground mb-1.5">
                    LinkedIn
                  </p>
                  {user.linkedin ? (
                    <a
                      href={user.linkedin}
                      target="_blank"
                      rel="noreferrer"
                      className="inline-flex items-center gap-1.5 text-sm hover:underline"
                      style={{ color: "#aa3bff" }}
                    >
                      <Link2 className="w-3.5 h-3.5" />
                      {user.linkedin}
                    </a>
                  ) : (
                    <p className="text-sm text-muted-foreground/60 italic">
                      Not set.
                    </p>
                  )}
                </div>

                <div>
                  <p className="text-[11px] font-semibold uppercase tracking-widest text-muted-foreground mb-1.5">
                    Website
                  </p>
                  {user.website ? (
                    <a
                      href={user.website}
                      target="_blank"
                      rel="noreferrer"
                      className="inline-flex items-center gap-1.5 text-sm hover:underline"
                      style={{ color: "#aa3bff" }}
                    >
                      <Link2 className="w-3.5 h-3.5" />
                      {user.website}
                    </a>
                  ) : (
                    <p className="text-sm text-muted-foreground/60 italic">
                      Not set.
                    </p>
                  )}
                </div>
              </div>
            )}
          </div>
        )}
      </main>
    </div>
  );
}
