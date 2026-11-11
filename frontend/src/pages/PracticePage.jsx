import { useCallback, useEffect, useState } from "react";
import { ApiError } from "../api/client";
import { startPractice, autosavePracticeAnswer, submitPractice } from "../api/practice";
import SusModal from "../components/SusModal";
import "./diagnostic.css";

const SUPABASE_URL = import.meta.env.VITE_SUPABASE_URL || "";
const DIAGRAM_BUCKET = "question-diagrams";

const SAVE_LABEL = {
  idle: "",
  saving: "Saving…",
  saved: "Saved",
  failed: "Saved locally (offline)",
};

/* LocalStorage Backup Helpers for Offline Resilience */
function getLocalBackup(sessionId) {
  if (!sessionId) return {};
  try {
    const raw = localStorage.getItem(`pathwise_practice_${sessionId}`);
    return raw ? JSON.parse(raw) : {};
  } catch {
    return {};
  }
}

function saveLocalBackup(sessionId, questionId, optionLabel) {
  if (!sessionId) return;
  try {
    const current = getLocalBackup(sessionId);
    current[questionId] = optionLabel;
    localStorage.setItem(`pathwise_practice_${sessionId}`, JSON.stringify(current));
  } catch (err) {
    console.warn("Could not save local practice backup:", err);
  }
}

function clearLocalBackup(sessionId) {
  if (!sessionId) return;
  try {
    localStorage.removeItem(`pathwise_practice_${sessionId}`);
  } catch {
    // Ignore cleanup errors
  }
}

function diagramSrc(path) {
  if (!path || !SUPABASE_URL) return null;
  const encoded = path.split("/").map(encodeURIComponent).join("/");
  return `${SUPABASE_URL.replace(/\/$/, "")}/storage/v1/object/public/${DIAGRAM_BUCKET}/${encoded}`;
}

function describeError(err) {
  if (err instanceof ApiError && err.message) return err.message;
  return "Something went wrong. Please try again.";
}

function Diagram({ path }) {
  const [failed, setFailed] = useState(false);
  if (!path) return null;

  const src = diagramSrc(path);
  if (!src || failed) {
    return <div className="dx-diagram-missing">Diagram unavailable</div>;
  }
  return (
    <a
      href={src}
      target="_blank"
      rel="noreferrer"
      title="Open the diagram at full size"
      style={{ display: "block", textAlign: "center", marginBottom: "16px" }}
    >
      <img
        className="dx-diagram"
        src={src}
        alt="Question diagram. Click to open at full size."
        onError={() => setFailed(true)}
        style={{
          display: "inline-block",
          maxHeight: "220px",
          maxWidth: "100%",
          width: "auto",
          height: "auto",
          objectFit: "contain",
        }}
      />
    </a>
  );
}

function TopBar({ subject, onExit, right }) {
  return (
    <header className="dx-topbar">
      <button type="button" className="btn-ghost dx-exit" onClick={onExit}>
        ← Dashboard
      </button>
      <div className="dx-subject">{subject} · Practice</div>
      <div className="dx-right">{right}</div>
    </header>
  );
}

function ScoreRing({ score }) {
  return (
    <div className="dx-ring" style={{ "--pct": `${score}%` }}>
      <div className="dx-ring-inner">
        <span className="dx-ring-value">{Math.round(score)}</span>
        <span className="dx-ring-unit">%</span>
      </div>
    </div>
  );
}

export default function PracticePage({ subject, onExit }) {
  const [phase, setPhase] = useState("loading"); // loading | active | submitting | results | error
  const [session, setSession] = useState(null);
  const [index, setIndex] = useState(0);
  const [answers, setAnswers] = useState({}); // question id -> option label
  const [saveState, setSaveState] = useState("idle");
  const [notice, setNotice] = useState("");
  const [loadError, setLoadError] = useState("");
  const [result, setResult] = useState(null);

  // Review Filter State ('all' | 'incorrect' | 'correct')
  const [reviewFilter, setReviewFilter] = useState("all");

  // SUS Modal evaluation state
  const [showSusModal, setShowSusModal] = useState(false);
  const [susSubmitted, setSusSubmitted] = useState(false);

  const questions = session?.questions ?? [];
  const total = questions.length;
  const current = questions[index];
  const answeredCount = Object.keys(answers).length;
  const unansweredCount = total - answeredCount;
  const isLast = total > 0 && index === total - 1;
  const progress = total ? ((index + 1) / total) * 100 : 0;
  const selected = current ? answers[current.id] : null;

  const load = useCallback(async () => {
    setPhase("loading");
    setLoadError("");
    setNotice("");
    try {
      const data = await startPractice(subject);
      const questionList = data.questions ?? [];

      // 1. Restore answers saved on server
      const validIds = new Set(questionList.map((q) => q.id));
      const serverAnswers = {};
      for (const saved of data.saved_answers ?? []) {
        if (validIds.has(saved.question_id) && saved.selected_option) {
          serverAnswers[saved.question_id] = saved.selected_option;
        }
      }

      // 2. Merge local offline backup on top (preserves unsynced local selections)
      const localBackup = getLocalBackup(data.session_id);
      const restored = { ...serverAnswers };
      for (const [qId, opt] of Object.entries(localBackup)) {
        if (validIds.has(qId) && opt) {
          restored[qId] = opt;
        }
      }

      // Open at the first unanswered question
      const firstOpen = questionList.findIndex((q) => !restored[q.id]);
      const startIndex =
        firstOpen === -1 ? Math.max(0, questionList.length - 1) : firstOpen;

      setSession(data);
      setAnswers(restored);
      setIndex(startIndex);
      setSaveState("idle");
      setPhase("active");
    } catch (err) {
      setLoadError(describeError(err));
      setPhase("error");
    }
  }, [subject]);

  useEffect(() => {
    load();
  }, [load]);

  const choose = async (label) => {
    if (!current || phase !== "active") return;
    const questionId = current.id;
    const sessionId = session.session_id;

    setAnswers((prev) => ({ ...prev, [questionId]: label }));
    saveLocalBackup(sessionId, questionId, label);
    setSaveState("saving");

    try {
      await autosavePracticeAnswer({
        sessionId,
        questionId,
        selectedOption: label,
      });
      setSaveState("saved");
      setNotice("");
    } catch {
      setNotice(
        "Network connection lost. Your answer is saved locally on this device and will be sent when you submit."
      );
      setSaveState("failed");
    }
  };

  const submit = async () => {
    if (
      unansweredCount > 0 &&
      !window.confirm(
        `${unansweredCount} question(s) are unanswered and will count as wrong. Submit anyway?`
      )
    ) {
      return;
    }

    const payload = questions
      .filter((q) => answers[q.id])
      .map((q) => ({ question_id: q.id, selected_option: answers[q.id] }));

    setPhase("submitting");
    setNotice("");
    try {
      const data = await submitPractice({
        sessionId: session.session_id,
        answers: payload,
      });
      clearLocalBackup(session.session_id);
      setResult(data);
      setPhase("results");
    } catch (err) {
      setNotice(describeError(err));
      setPhase("active");
    }
  };

  if (phase === "loading") {
    return (
      <main className="dx-page">
        <TopBar subject={subject} onExit={onExit} />
        <section className="dx-card dx-loading">
          <div className="dx-skel dx-skel--title" />
          <div className="dx-skel" />
          <div className="dx-skel" />
          <div className="dx-skel" />
        </section>
      </main>
    );
  }

  if (phase === "error") {
    return (
      <main className="dx-page">
        <TopBar subject={subject} onExit={onExit} />
        <section className="dx-card dx-center">
          <h2>Couldn't start practice</h2>
          <p className="dx-muted">{loadError}</p>
          <div className="dx-actions">
            <button type="button" className="btn-primary" onClick={load}>
              Try again
            </button>
            <button type="button" className="btn-ghost" onClick={onExit}>
              Back to dashboard
            </button>
          </div>
        </section>
      </main>
    );
  }

  if (phase === "results" && result) {
    const correctTotal = result.topic_breakdown.reduce((sum, t) => sum + t.correct_count, 0);
    const reviews = result.question_reviews || [];
    const weakTopics = result.topic_breakdown.filter((t) => t.percentage < 60);

    const filteredReviews = reviews.filter((q) => {
      if (reviewFilter === "incorrect") return !q.is_correct;
      if (reviewFilter === "correct") return q.is_correct;
      return true;
    });

    return (
      <main className="dx-page">
        <TopBar subject={subject} onExit={onExit} />
        <section className="dx-card dx-results">
          <p className="dx-eyebrow">Practice complete</p>
          <h2>{result.subject}</h2>

          <div className="dx-result-top">
            <ScoreRing score={result.score} />
            <div className="dx-result-meta">
              <div>
                <span className="dx-label">Tier now</span>
                <span className="dx-tier">{result.new_tier}</span>
              </div>
              <div>
                <span className="dx-label">Started at</span>
                <span>{result.target_tier}</span>
              </div>
              <div>
                <span className="dx-label">WAEC grade</span>
                <span className="dx-grade">{result.waec_grade}</span>
              </div>
              <div>
                <span className="dx-label">Correct</span>
                <span>{correctTotal} of {total}</span>
              </div>
            </div>
          </div>

          {/* Remediation Bridge: Weak Topics Notice */}
          {weakTopics.length > 0 && (
            <div
              style={{
                margin: "20px 0",
                padding: "16px 20px",
                background: "rgba(239, 68, 68, 0.1)",
                border: "1px solid rgba(239, 68, 68, 0.3)",
                borderRadius: "12px",
              }}
            >
              <h4 style={{ margin: "0 0 6px", color: "#fca5a5", fontSize: "0.95rem" }}>
                ⚠️ Study Path Revision Needed
              </h4>
              <p style={{ margin: "0 0 12px", color: "#e2e8f0", fontSize: "0.825rem", lineHeight: 1.4 }}>
                You scored under 60% in the following topic(s). Review the AI explanations below or access AI Study Notes from your dashboard.
              </p>
              <div style={{ display: "flex", flexWrap: "wrap", gap: "8px" }}>
                {weakTopics.map((wt) => (
                  <span
                    key={wt.topic_code}
                    style={{
                      fontSize: "12px",
                      padding: "4px 10px",
                      borderRadius: "6px",
                      background: "rgba(239, 68, 68, 0.2)",
                      border: "1px solid rgba(239, 68, 68, 0.4)",
                      color: "#fecdd3",
                      fontWeight: 600,
                    }}
                  >
                    {wt.topic_name} ({wt.percentage}%)
                  </span>
                ))}
              </div>
            </div>
          )}

          <h3 className="dx-section-title">Topic Breakdown</h3>
          <ul className="dx-topics">
            {result.topic_breakdown.map((t, i) => (
              <li key={t.topic_code} className="dx-topic" style={{ animationDelay: `${i * 70}ms` }}>
                <div className="dx-topic-head">
                  <span>{t.topic_name}</span>
                  <span>{t.correct_count}/{t.total_count}</span>
                </div>
                <div className="dx-bar">
                  <div className="dx-bar-fill" style={{ "--w": `${t.percentage}%` }} />
                </div>
              </li>
            ))}
          </ul>

          {/* Interactive Question Review Section */}
          {reviews.length > 0 && (
            <div style={{ marginTop: "32px" }}>
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  marginBottom: "16px",
                  flexWrap: "wrap",
                  gap: "12px",
                }}
              >
                <h3 className="dx-section-title" style={{ margin: 0 }}>
                  Question Review & Step-by-Step Solutions
                </h3>
                <div style={{ display: "flex", gap: "6px" }}>
                  <button
                    type="button"
                    className={`btn-ghost ${reviewFilter === "all" ? "active" : ""}`}
                    style={{
                      fontSize: "12px",
                      padding: "4px 10px",
                      background: reviewFilter === "all" ? "rgba(56, 189, 248, 0.2)" : undefined,
                      borderColor: reviewFilter === "all" ? "#38bdf8" : undefined,
                    }}
                    onClick={() => setReviewFilter("all")}
                  >
                    All ({reviews.length})
                  </button>
                  <button
                    type="button"
                    className={`btn-ghost ${reviewFilter === "incorrect" ? "active" : ""}`}
                    style={{
                      fontSize: "12px",
                      padding: "4px 10px",
                      background: reviewFilter === "incorrect" ? "rgba(239, 68, 68, 0.2)" : undefined,
                      borderColor: reviewFilter === "incorrect" ? "#ef4444" : undefined,
                    }}
                    onClick={() => setReviewFilter("incorrect")}
                  >
                    Incorrect ({reviews.filter((q) => !q.is_correct).length})
                  </button>
                  <button
                    type="button"
                    className={`btn-ghost ${reviewFilter === "correct" ? "active" : ""}`}
                    style={{
                      fontSize: "12px",
                      padding: "4px 10px",
                      background: reviewFilter === "correct" ? "rgba(34, 197, 94, 0.2)" : undefined,
                      borderColor: reviewFilter === "correct" ? "#22c55e" : undefined,
                    }}
                    onClick={() => setReviewFilter("correct")}
                  >
                    Correct ({reviews.filter((q) => q.is_correct).length})
                  </button>
                </div>
              </div>

              <div style={{ display: "flex", flexDirection: "column", gap: "20px" }}>
                {filteredReviews.map((q, idx) => (
                  <div
                    key={q.question_id || idx}
                    style={{
                      background: "rgba(15, 23, 42, 0.6)",
                      border: `1px solid ${q.is_correct ? "rgba(34, 197, 94, 0.3)" : "rgba(239, 68, 68, 0.3)"}`,
                      borderRadius: "12px",
                      padding: "18px",
                    }}
                  >
                    <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "10px" }}>
                      <span className="dx-chip">{q.topic_name}</span>
                      <span
                        style={{
                          fontSize: "12px",
                          fontWeight: 700,
                          color: q.is_correct ? "#4ade80" : "#f87171",
                          padding: "2px 8px",
                          borderRadius: "4px",
                          background: q.is_correct ? "rgba(34, 197, 94, 0.15)" : "rgba(239, 68, 68, 0.15)",
                        }}
                      >
                        {q.is_correct ? "✓ Correct" : "✗ Incorrect"}
                      </span>
                    </div>

                    <p style={{ color: "#f8fafc", fontSize: "0.95rem", fontWeight: 500, margin: "0 0 12px" }}>
                      {idx + 1}. {q.question_text}
                    </p>

                    <Diagram path={q.diagram_url} />

                    <div style={{ display: "grid", gap: "8px", marginBottom: "14px" }}>
                      {q.options.map((opt) => {
                        const isUserChoice = q.selected_option === opt.label;
                        const isCorrectChoice = q.correct_option === opt.label;

                        let style = {
                          display: "flex",
                          alignItems: "center",
                          gap: "10px",
                          padding: "10px 12px",
                          borderRadius: "8px",
                          background: "rgba(30, 41, 59, 0.5)",
                          border: "1px solid rgba(148, 163, 184, 0.15)",
                          color: "#cbd5e1",
                          fontSize: "0.875rem",
                        };

                        if (isCorrectChoice) {
                          style.background = "rgba(34, 197, 94, 0.18)";
                          style.borderColor = "#22c55e";
                          style.color = "#f8fafc";
                        } else if (isUserChoice && !q.is_correct) {
                          style.background = "rgba(239, 68, 68, 0.18)";
                          style.borderColor = "#ef4444";
                          style.color = "#f8fafc";
                        }

                        return (
                          <div key={opt.label} style={style}>
                            <strong style={{ minWidth: "20px" }}>{opt.label}.</strong>
                            <span style={{ flex: 1 }}>{opt.text}</span>
                            {isUserChoice && (
                              <span style={{ fontSize: "11px", fontWeight: 600, opacity: 0.9 }}>
                                {q.is_correct ? "(Your Choice - Correct)" : "(Your Choice)"}
                              </span>
                            )}
                            {!isUserChoice && isCorrectChoice && (
                              <span style={{ fontSize: "11px", fontWeight: 600, color: "#4ade80" }}>
                                (Correct Answer)
                              </span>
                            )}
                          </div>
                        );
                      })}
                    </div>

                    {/* Step-by-Step WAEC Explanation Box */}
                    <div
                      style={{
                        background: "rgba(30, 41, 59, 0.8)",
                        borderLeft: "3px solid #38bdf8",
                        borderRadius: "0 8px 8px 0",
                        padding: "12px 14px",
                        fontSize: "0.85rem",
                        color: "#94a3b8",
                      }}
                    >
                      <strong style={{ color: "#38bdf8", display: "block", marginBottom: "4px" }}>
                        Step-by-Step WAEC Solution:
                      </strong>
                      <p style={{ margin: 0, lineHeight: 1.5, color: "#e2e8f0" }}>{q.explanation}</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* SUS Usability Invitation inside Practice Results */}
          {!susSubmitted && (
            <div
              style={{
                marginTop: "24px",
                padding: "16px",
                background: "linear-gradient(135deg, rgba(56, 189, 248, 0.12), rgba(139, 92, 246, 0.12))",
                border: "1px solid rgba(56, 189, 248, 0.3)",
                borderRadius: "10px",
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                gap: "12px",
                flexWrap: "wrap",
              }}
            >
              <div>
                <span style={{ fontSize: "0.85rem", fontWeight: 600, color: "#f8fafc", display: "block" }}>
                  Rate your Path-Wise learning experience
                </span>
                <span style={{ fontSize: "0.775rem", color: "#94a3b8" }}>
                  10 short questions to support our Chapter 5 usability research.
                </span>
              </div>
              <button
                type="button"
                className="btn-primary"
                style={{ fontSize: "12px", padding: "6px 14px" }}
                onClick={() => setShowSusModal(true)}
              >
                Evaluate Usability
              </button>
            </div>
          )}

          <div className="dx-actions" style={{ marginTop: "24px" }}>
            <button type="button" className="btn-primary" onClick={onExit}>
              Back to dashboard
            </button>
          </div>
        </section>

        <SusModal
          isOpen={showSusModal}
          onClose={() => setShowSusModal(false)}
          onSubmitted={() => setSusSubmitted(true)}
        />
      </main>
    );
  }

  return (
    <main className="dx-page">
      <TopBar
        subject={subject}
        onExit={onExit}
        right={<span className={`dx-save dx-save--${saveState}`}>{SAVE_LABEL[saveState]}</span>}
      />

      <div className="dx-progress">
        <div className="dx-progress-meta">
          <span>Question {index + 1} of {total}</span>
          <span>{answeredCount} answered</span>
        </div>
        <div className="dx-progress-track">
          <div className="dx-progress-fill" style={{ width: `${progress}%` }} />
        </div>
      </div>

      {notice && <div className="dx-notice" role="alert">{notice}</div>}

      {current && (
        <section key={current.id} className="dx-card dx-question">
          <div className="dx-chip">{current.topic_name}</div>
          <p className="dx-qtext">{current.question_text}</p>
          <Diagram path={current.diagram_url} />

          <div className="dx-options">
            {current.options.map((opt) => {
              const isSelected = selected === opt.label;
              return (
                <button
                  key={opt.label}
                  type="button"
                  className={`dx-option${isSelected ? " dx-option--selected" : ""}`}
                  onClick={() => choose(opt.label)}
                  disabled={phase === "submitting"}
                  aria-pressed={isSelected}
                >
                  <span className="dx-letter">{opt.label}</span>
                  <span className="dx-option-text">{opt.text}</span>
                </button>
              );
            })}
          </div>
        </section>
      )}

      <nav className="dx-nav">
        <button
          type="button"
          className="btn-ghost"
          onClick={() => setIndex((i) => Math.max(0, i - 1))}
          disabled={index === 0}
        >
          Previous
        </button>

        <div className="dx-dots">
          {questions.map((q, i) => {
            const classes = ["dx-dot"];
            if (i === index) classes.push("dx-dot--current");
            if (answers[q.id]) classes.push("dx-dot--done");
            return (
              <button
                key={q.id}
                type="button"
                aria-label={`Go to question ${i + 1}`}
                className={classes.join(" ")}
                onClick={() => setIndex(i)}
              />
            );
          })}
        </div>

        {isLast ? (
          <button
            type="button"
            className="btn-primary"
            onClick={submit}
            disabled={phase === "submitting"}
          >
            Submit practice
          </button>
        ) : (
          <button
            type="button"
            className="btn-primary"
            onClick={() => setIndex((i) => Math.min(total - 1, i + 1))}
          >
            Next
          </button>
        )}
      </nav>

      {phase === "submitting" && (
        <div className="dx-overlay">
          <div className="spinner" />
          <p>Marking your practice…</p>
        </div>
      )}
    </main>
  );
}