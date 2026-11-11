import { useCallback, useEffect, useState } from "react";
import { ApiError } from "../api/client";
import {
  startDiagnostic,
  autosaveDiagnosticAnswer,
  submitDiagnostic,
} from "../api/diagnostic";
import "./diagnostic.css";

const SUPABASE_URL = import.meta.env.VITE_SUPABASE_URL || "";
const DIAGRAM_BUCKET = "question-diagrams";

const SAVE_LABEL = {
  idle: "",
  saving: "Saving…",
  saved: "Saved",
  failed: "Not saved to server",
};

function diagramSrc(path) {
  if (!path || !SUPABASE_URL) return null;
  const encoded = path.split("/").map(encodeURIComponent).join("/");
  return `${SUPABASE_URL.replace(/\/$/, "")}/storage/v1/object/public/${DIAGRAM_BUCKET}/${encoded}`;
}

function describeError(err) {
  if (err instanceof ApiError && err.status === 410) {
    return "This diagnostic expired after 14 days of inactivity. Go back and start a new one.";
  }
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
      <div className="dx-subject">{subject}</div>
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

export default function DiagnosticPage({ subject, onExit }) {
  const [phase, setPhase] = useState("loading"); // loading | active | submitting | results | error
  const [attempt, setAttempt] = useState(null);
  const [index, setIndex] = useState(0);
  const [answers, setAnswers] = useState({}); // question id -> option label
  const [saveState, setSaveState] = useState("idle");
  const [notice, setNotice] = useState("");
  const [loadError, setLoadError] = useState("");
  const [expired, setExpired] = useState(false);
  const [result, setResult] = useState(null);

  const questions = attempt?.questions ?? [];
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
    setExpired(false);
    try {
      const data = await startDiagnostic(subject);
      const questionList = data.questions ?? [];

      // Restore choices saved on the server for this attempt (resume case).
      // Only keep answers that belong to a question in this attempt.
      const validIds = new Set(questionList.map((q) => q.id));
      const restored = {};
      for (const saved of data.saved_answers ?? []) {
        if (validIds.has(saved.question_id) && saved.selected_option) {
          restored[saved.question_id] = saved.selected_option;
        }
      }

      // Open at the first unanswered question. If everything is answered,
      // open the last question so the submit button is in view.
      const firstOpen = questionList.findIndex((q) => !restored[q.id]);
      const startIndex =
        firstOpen === -1 ? Math.max(0, questionList.length - 1) : firstOpen;

      setAttempt(data);
      setAnswers(restored);
      setIndex(startIndex);
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
    if (!current || expired || phase !== "active") return;
    const questionId = current.id;

    setAnswers((prev) => ({ ...prev, [questionId]: label }));
    setSaveState("saving");

    try {
      await autosaveDiagnosticAnswer({
        attemptId: attempt.attempt_id,
        questionId,
        selectedOption: label,
      });
      setSaveState("saved");
    } catch (err) {
      if (err instanceof ApiError && err.status === 410) {
        setExpired(true);
        setNotice(describeError(err));
      } else {
        setNotice("That answer didn't reach the server. It is still kept on this screen and will be included when you submit.");
      }
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
      const data = await submitDiagnostic({
        attemptId: attempt.attempt_id,
        answers: payload,
      });
      setResult(data);
      setPhase("results");
    } catch (err) {
      if (err instanceof ApiError && err.status === 410) setExpired(true);
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
          <h2>Couldn't start the diagnostic</h2>
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
    return (
      <main className="dx-page">
        <TopBar subject={subject} onExit={onExit} />
        <section className="dx-card dx-results">
          <p className="dx-eyebrow">Diagnostic complete</p>
          <h2>{result.subject}</h2>

          <div className="dx-result-top">
            <ScoreRing score={result.score} />
            <div className="dx-result-meta">
              <div>
                <span className="dx-label">Tier</span>
                <span className="dx-tier">{result.assigned_tier}</span>
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

          <h3 className="dx-section-title">Topic breakdown</h3>
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

          <div className="dx-actions">
            <button type="button" className="btn-primary" onClick={onExit}>
              Back to dashboard
            </button>
          </div>
        </section>
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
                  disabled={expired || phase === "submitting"}
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
            disabled={expired || phase === "submitting"}
          >
            Submit diagnostic
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
          <p>Marking your diagnostic…</p>
        </div>
      )}
    </main>
  );
}