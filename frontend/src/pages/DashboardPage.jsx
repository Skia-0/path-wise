import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "../api/client";
import SusModal from "../components/SusModal";
import "./dashboard.css";
import "./add-subject.css";
import "./subject-manage.css";

const ALL_SUBJECTS = ["Core Mathematics", "Elective Physics"];

function firstName(me) {
  const name = (me?.full_name || "").trim();
  if (name) return name.split(/\s+/)[0];
  return (me?.email || "there").split("@")[0];
}

function subjectState(subject) {
  if (subject.diagnostic_completed) return "completed";
  if (subject.has_open_diagnostic) return "open";
  return "new";
}

const PILL = {
  completed: { label: "Completed", className: "pill--ok" },
  open: { label: "In progress", className: "pill--progress" },
  new: { label: "Diagnostic needed", className: "pill--todo" },
};

function SubjectCard({
  subject,
  index,
  canRemove,
  removing,
  onStartDiagnostic,
  onStartPractice,
  onRemove,
}) {
  const state = subjectState(subject);
  const pill = PILL[state];

  const practiceReady = Boolean(subject.diagnostic_completed);
  const canPractice = practiceReady && typeof onStartPractice === "function";

  return (
    <article
      className={`subject-card${state === "completed" ? " subject-card--done" : ""}`}
      style={{ animationDelay: `${index * 90}ms` }}
    >
      <div className="subject-top">
        <h3>{subject.subject}</h3>
        <span className={`pill ${pill.className}`}>{pill.label}</span>
      </div>

      <div className="subject-tier">
        <span className="subject-tier-label">Current tier</span>
        <span className="subject-tier-value">{subject.current_tier}</span>
      </div>

      {/* BKT Skill Mastery Progress Bars */}
      {subject.all_topics && subject.all_topics.length > 0 && (
        <div style={{ margin: "16px 0 8px" }}>
          <span
            style={{
              fontSize: "11px",
              textTransform: "uppercase",
              letterSpacing: "0.08em",
              color: "var(--accent, #38bdf8)",
              fontWeight: 700,
              display: "block",
              marginBottom: "10px",
            }}
          >
            BKT Skill Mastery Engine
          </span>

          <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
            {subject.all_topics.slice(0, 5).map((t) => (
              <div key={t.topic_code}>
                <div
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    fontSize: "12px",
                    color: "#e2e8f0",
                    marginBottom: "4px",
                  }}
                >
                  <span style={{ fontWeight: 500 }}>{t.topic_name}</span>
                  <span
                    style={{
                      fontWeight: 700,
                      color: t.percentage >= 60 ? "#4ade80" : "#f87171",
                    }}
                  >
                    {t.percentage}%
                  </span>
                </div>
                <div
                  style={{
                    height: "7px",
                    background: "rgba(15, 23, 42, 0.7)",
                    borderRadius: "999px",
                    overflow: "hidden",
                    border: "1px solid rgba(148, 163, 184, 0.2)",
                  }}
                >
                  <div
                    style={{
                      height: "100%",
                      width: `${t.percentage}%`,
                      background:
                        t.percentage >= 60
                          ? "linear-gradient(90deg, #22c55e, #4ade80)"
                          : "linear-gradient(90deg, #ef4444, #f87171)",
                      borderRadius: "999px",
                      transition: "width 0.5s ease",
                    }}
                  />
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="subject-actions" style={{ marginTop: "16px" }}>
        {state === "completed" && (
          <p className="subject-note">
            Diagnostic finished. Practice updates your BKT skill levels in real time.
          </p>
        )}

        {!practiceReady && (
          <p className="subject-note">Finish the diagnostic to unlock practice.</p>
        )}

        {state === "open" && (
          <button
            type="button"
            className="btn-primary"
            onClick={() => onStartDiagnostic(subject.subject)}
          >
            Continue
          </button>
        )}

        {state === "new" && (
          <button
            type="button"
            className="btn-primary"
            onClick={() => onStartDiagnostic(subject.subject)}
          >
            Start diagnostic
          </button>
        )}

        {canPractice ? (
          <button
            type="button"
            className="btn-primary"
            onClick={() => onStartPractice(subject.subject)}
          >
            {subject.has_open_practice ? "Continue practice" : "Practice"}
          </button>
        ) : (
          <button type="button" className="btn-ghost" disabled>
            Practice
          </button>
        )}
      </div>

      {canRemove && (
        <button
          type="button"
          className="subject-remove"
          onClick={() => onRemove(subject.subject)}
          disabled={removing}
        >
          {removing ? "Removing..." : "Remove from dashboard"}
        </button>
      )}
    </article>
  );
}

function AddSubjectPanel({ missingSubjects, onAdded }) {
  const [adding, setAdding] = useState("");
  const [error, setError] = useState("");

  async function handleAdd(subject) {
    setError("");
    setAdding(subject);
    try {
      await api.post("/dashboard/subjects/add", { subject });
      onAdded();
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        onAdded();
      } else {
        setError(err instanceof ApiError ? err.message : "Could not add the subject. Try again.");
      }
    } finally {
      setAdding("");
    }
  }

  return (
    <section className="add-subject" aria-labelledby="add-subject-title">
      <div className="add-subject-head">
        <h2 id="add-subject-title">Add a subject</h2>
        <p>Start another WAEC subject with its own diagnostic, study path and practice.</p>
      </div>

      <div className="add-subject-options">
        {missingSubjects.map((subject) => (
          <button
            key={subject}
            type="button"
            className="add-subject-btn"
            onClick={() => handleAdd(subject)}
            disabled={Boolean(adding)}
          >
            {adding === subject ? (
              <span className="spinner" aria-hidden="true" />
            ) : (
              <span className="add-subject-plus" aria-hidden="true">+</span>
            )}
            <span>{adding === subject ? "Adding..." : `Add ${subject}`}</span>
          </button>
        ))}
      </div>

      {error && (
        <p key={error} role="alert" className="alert-error">
          {error}
        </p>
      )}
    </section>
  );
}

export default function DashboardPage({ onSignOut, onStartDiagnostic, onStartPractice }) {
  const [me, setMe] = useState(null);
  const [subjects, setSubjects] = useState(null);
  const [error, setError] = useState("");
  const [actionError, setActionError] = useState("");
  const [removing, setRemoving] = useState("");
  const [loading, setLoading] = useState(true);

  // SUS Evaluation state
  const [showSusModal, setShowSusModal] = useState(false);
  const [susStatus, setSusStatus] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [profile, subjectData, susInfo] = await Promise.all([
        api.get("/auth/me"),
        api.get("/dashboard/subjects"),
        api.get("/evaluation/sus/status").catch(() => ({ completed: false })),
      ]);

      const loadedSubjects = subjectData.subjects || [];

      // Fetch study path focus areas and BKT topics for completed subjects
      const pathPromises = loadedSubjects.map(async (s) => {
        if (s.diagnostic_completed) {
          try {
            const sp = await api.get(`/studypath/${encodeURIComponent(s.subject)}`);
            return {
              ...s,
              focus_topics: sp.focus_topics || [],
              all_topics: sp.all_topics || [],
            };
          } catch (err) {
            console.warn("Failed to load study path:", err);
            return { ...s, focus_topics: [], all_topics: [] };
          }
        }
        return { ...s, focus_topics: [], all_topics: [] };
      });

      const subjectsWithPaths = await Promise.all(pathPromises);

      setMe(profile);
      setSubjects(subjectsWithPaths);
      setSusStatus(susInfo);
    } catch (err) {
      setError(err.message || "Could not load your dashboard.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function handleRemove(subjectName) {
    const confirmed = window.confirm(
      `Remove ${subjectName} from your dashboard?\n\n` +
        `Your progress is kept. You can add it back at any time from "Add a subject".`
    );
    if (!confirmed) return;

    setActionError("");
    setRemoving(subjectName);
    try {
      await api.post("/dashboard/subjects/archive", { subject: subjectName });
      await load();
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : "Could not remove the subject. Try again.");
    } finally {
      setRemoving("");
    }
  }

  const visibleCount = subjects ? subjects.length : 0;
  const canRemove = visibleCount > 1;

  const missingSubjects = subjects
    ? ALL_SUBJECTS.filter((name) => !subjects.some((s) => s.subject === name))
    : [];

  return (
    <main className="dash">
      <header className="dash-header">
        <h1 className="dash-greeting">
          Hi, <span>{me ? firstName(me) : "there"}</span>
        </h1>
        <div style={{ display: "flex", gap: "10px", alignItems: "center" }}>
          <button
            type="button"
            className="btn-ghost"
            style={{ fontSize: "13px", padding: "6px 12px" }}
            onClick={() => setShowSusModal(true)}
          >
            {susStatus?.completed ? "Usability Survey (Done)" : "Evaluate App Usability"}
          </button>
          <button type="button" className="btn-signout" onClick={onSignOut}>
            Sign out
          </button>
        </div>
      </header>

      {/* Usability Evaluation Invitation Banner if not completed */}
      {susStatus && !susStatus.completed && (
        <div
          style={{
            background: "linear-gradient(135deg, rgba(56, 189, 248, 0.15), rgba(139, 92, 246, 0.15))",
            border: "1px solid rgba(56, 189, 248, 0.3)",
            borderRadius: "12px",
            padding: "16px 20px",
            marginBottom: "24px",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            flexWrap: "wrap",
            gap: "12px",
          }}
        >
          <div>
            <h4 style={{ margin: 0, color: "#f8fafc", fontSize: "0.95rem" }}>
              Help Us Evaluate Path-Wise
            </h4>
            <p style={{ margin: "4px 0 0", color: "#94a3b8", fontSize: "0.825rem" }}>
              Take our 2-minute System Usability Scale (SUS) survey to support our study.
            </p>
          </div>
          <button
            type="button"
            className="btn-primary"
            style={{ fontSize: "13px", padding: "8px 16px" }}
            onClick={() => setShowSusModal(true)}
          >
            Start 10-Item Survey
          </button>
        </div>
      )}

      {error && (
        <div className="dash-error">
          <p>{error}</p>
          <button type="button" className="btn-primary" onClick={load}>
            Try again
          </button>
        </div>
      )}

      {actionError && (
        <p key={actionError} role="alert" className="alert-error dash-action-error">
          {actionError}
        </p>
      )}

      {loading && !subjects && (
        <div className="dash-grid">
          {[0, 1].map((i) => (
            <div key={i} className="dash-skel">
              <div className="skeleton skeleton--title" />
              <div className="skeleton skeleton--short" />
              <div className="skeleton skeleton--btn" />
            </div>
          ))}
        </div>
      )}

      {subjects && subjects.length > 0 && (
        <div className="dash-grid">
          {subjects.map((s, i) => (
            <SubjectCard
              key={s.subject}
              subject={s}
              index={i}
              canRemove={canRemove}
              removing={removing === s.subject}
              onStartDiagnostic={onStartDiagnostic}
              onStartPractice={onStartPractice}
              onRemove={handleRemove}
            />
          ))}
        </div>
      )}

      {subjects && subjects.length === 0 && !error && (
        <p className="dash-empty">No subjects are set up for this account yet.</p>
      )}

      {subjects && missingSubjects.length > 0 && (
        <AddSubjectPanel missingSubjects={missingSubjects} onAdded={load} />
      )}

      {/* SUS Evaluation Modal */}
      <SusModal
        isOpen={showSusModal}
        onClose={() => setShowSusModal(false)}
        onSubmitted={() => {
          load();
        }}
      />
    </main>
  );
}