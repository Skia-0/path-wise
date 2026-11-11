import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import { fetchTopicNotes } from "../api/notes";
import "./notes.css";

const ALL_SUBJECTS = ["Core Mathematics", "Elective Physics"];

/**
 * Split AI note strings like:
 *   "Linear Inequality: A mathematical statement..."
 *   "WAEC Trap 1: Students forget to flip the sign..."
 * into { title, body }.
 * Falls back cleanly if there is no colon separator.
 */
function parseNoteItem(raw) {
  if (raw == null) return { title: "", body: "" };
  const text = String(raw).trim();
  if (!text) return { title: "", body: "" };

  // Prefer " :: " if present (future-proof), else first ": "
  if (text.includes("::")) {
    const parts = text.split("::").map((s) => s.trim()).filter(Boolean);
    if (parts.length >= 2) {
      return {
        title: parts[0],
        body: parts.slice(1).join(" — "),
      };
    }
  }

  const colonIdx = text.indexOf(":");
  if (colonIdx > 0 && colonIdx < 80) {
    const title = text.slice(0, colonIdx).trim();
    const body = text.slice(colonIdx + 1).trim();
    // Avoid treating math ratios like "1:2" or times as titles
    if (title.length >= 3 && body.length >= 8) {
      return { title, body };
    }
  }

  return { title: "", body: text };
}

function FormattedNoteView({ note }) {
  const data = note.rawResponse || {};

  const summaryText =
    data.summary_text ||
    data.summary ||
    (typeof note.summary === "string" ? note.summary : "");

  const definitions = data.key_definitions || [];
  const formulas = data.essential_formulas || [];
  const traps = data.common_waec_traps || data.common_traps || [];
  const tips = data.step_by_step_exam_tips || data.exam_tips || [];

  return (
    <div className="notes-structured">
      {/* Meta chips */}
      <div className="note-meta-row">
        <span className="note-chip note-chip--subject">{note.subject}</span>
        <span className="note-chip note-chip--paper">Paper 1 &amp; 2</span>
        <span className="note-chip note-chip--yield">High-yield topic</span>
      </div>

      {summaryText && (
        <section className="note-section note-section--overview">
          <h4 className="note-section-title">📌 Topic Overview</h4>
          <p className="note-text">{summaryText}</p>
        </section>
      )}

      {definitions.length > 0 && (
        <section className="note-section">
          <h4 className="note-section-title">📖 Key Definitions &amp; Laws</h4>
          <div className="note-def-grid">
            {definitions.map((item, i) => {
              const { title, body } = parseNoteItem(item);
              return (
                <article key={i} className="note-def-card">
                  {title ? (
                    <span className="note-def-term">{title}</span>
                  ) : (
                    <span className="note-def-term">Definition {i + 1}</span>
                  )}
                  <p className="note-def-body">{body}</p>
                </article>
              );
            })}
          </div>
        </section>
      )}

      {formulas.length > 0 && (
        <section className="note-section">
          <h4 className="note-section-title">🧮 Essential Formulas &amp; Rules</h4>
          <div className="note-formulas">
            {formulas.map((item, i) => {
              const { title, body } = parseNoteItem(item);
              return (
                <div key={i} className="note-formula-card">
                  {title && <div className="note-formula-label">{title}</div>}
                  <div className="note-formula-box">{body || String(item)}</div>
                </div>
              );
            })}
          </div>
        </section>
      )}

      {traps.length > 0 && (
        <section className="note-section note-section--traps">
          <h4 className="note-section-title">⚠️ Common WAEC Traps &amp; Mistakes</h4>
          <div className="note-traps-list">
            {traps.map((item, i) => {
              const { title, body } = parseNoteItem(item);
              return (
                <article key={i} className="note-trap-card">
                  <div className="note-trap-header">
                    <span className="note-trap-badge">Trap {i + 1}</span>
                    {title && <h5 className="note-trap-title">{title}</h5>}
                  </div>
                  <p className="note-trap-body">{body || String(item)}</p>
                </article>
              );
            })}
          </div>
        </section>
      )}

      {tips.length > 0 && (
        <section className="note-section note-section--tips">
          <h4 className="note-section-title">🎯 Step-by-Step Exam &amp; Method Tips</h4>
          <ol className="note-tips-timeline">
            {tips.map((item, i) => {
              const { title, body } = parseNoteItem(item);
              const stepNum = String(i + 1).padStart(2, "0");
              return (
                <li key={i} className="note-tip-item">
                  <span className="note-tip-num" aria-hidden="true">
                    {stepNum}
                  </span>
                  <div className="note-tip-content">
                    {title && <h5 className="note-tip-title">{title}</h5>}
                    <p className="note-tip-body">{body || String(item)}</p>
                  </div>
                </li>
              );
            })}
          </ol>
        </section>
      )}
    </div>
  );
}

export default function NotesPage({ initialSubject = "Core Mathematics", onExit }) {
  const [subject, setSubject] = useState(initialSubject);
  const [topics, setTopics] = useState([]);
  const [selectedTopic, setSelectedTopic] = useState("");
  const [loadingTopics, setLoadingTopics] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState("");
  const [mismatchError, setMismatchError] = useState("");
  const [currentNote, setCurrentNote] = useState(null);
  const [history, setHistory] = useState([]);

  const loadTopics = useCallback(async (sub) => {
    setLoadingTopics(true);
    setError("");
    setMismatchError("");
    try {
      const res = await api.get(`/studypath/${encodeURIComponent(sub)}`);
      const all = res.all_topics || [];
      setTopics(all);
      if (all.length > 0) {
        setSelectedTopic(all[0].topic_code);
      } else {
        setSelectedTopic("");
      }
    } catch (err) {
      setError(err.message || "Could not load topics for this subject.");
    } finally {
      setLoadingTopics(false);
    }
  }, []);

  useEffect(() => {
    loadTopics(subject);
  }, [subject, loadTopics]);

  async function handleGenerate() {
    if (!selectedTopic) return;

    const topicObj = topics.find((t) => t.topic_code === selectedTopic);
    if (!topicObj) {
      setMismatchError(`Selected topic does not belong to ${subject}.`);
      return;
    }

    setGenerating(true);
    setError("");
    setMismatchError("");

    try {
      const res = await fetchTopicNotes(subject, selectedTopic);
      const noteItem = {
        id: `${subject}-${selectedTopic}-${Date.now()}`,
        subject: res.subject || subject,
        topicCode: res.topic_code || selectedTopic,
        topicName: topicObj.topic_name,
        summary: res.summary_text || res.summary || "",
        rawResponse: res,
        isAiGenerated: res.is_ai_generated ?? true,
        timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
      };

      setCurrentNote(noteItem);
      setHistory((prev) => [noteItem, ...prev.filter((h) => h.id !== noteItem.id)]);
    } catch (err) {
      if (err.message && err.message.toLowerCase().includes("mismatch")) {
        setMismatchError(err.message);
      } else {
        setError(err.message || "Failed to generate AI study notes.");
      }
    } finally {
      setGenerating(false);
    }
  }

  return (
    <main className="notes-page">
      <header className="notes-header">
        <button type="button" className="btn-ghost" onClick={onExit}>
          ← Dashboard
        </button>
        <h2>AI Study Notes</h2>
        <div />
      </header>

      <section className="notes-controls">
        <div className="notes-field">
          <label htmlFor="notes-subject">Subject</label>
          <select
            id="notes-subject"
            className="notes-select"
            value={subject}
            onChange={(e) => setSubject(e.target.value)}
          >
            {ALL_SUBJECTS.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </div>

        <div className="notes-field">
          <label htmlFor="notes-topic">Topic</label>
          <select
            id="notes-topic"
            className="notes-select"
            value={selectedTopic}
            onChange={(e) => setSelectedTopic(e.target.value)}
            disabled={loadingTopics || topics.length === 0}
          >
            {topics.map((t) => (
              <option key={t.topic_code} value={t.topic_code}>
                {t.topic_name}
              </option>
            ))}
          </select>
        </div>

        <button
          type="button"
          className="btn-primary notes-gen-btn"
          onClick={handleGenerate}
          disabled={generating || loadingTopics || !selectedTopic}
        >
          {generating ? "Summarising..." : "Generate Notes"}
        </button>
      </section>

      {mismatchError && (
        <div className="notes-mismatch-banner" role="alert">
          ⚠️ <strong>Subject Mismatch Warning:</strong> {mismatchError}
        </div>
      )}

      {error && (
        <div className="alert-error" role="alert">
          {error}
        </div>
      )}

      {currentNote && (
        <article className="notes-card">
          <div className="notes-card-meta">
            <div>
              <h3>{currentNote.topicName}</h3>
              <p className="dx-muted">{currentNote.subject}</p>
            </div>
            {currentNote.isAiGenerated && (
              <span className="notes-ai-badge">✦ Gemini AI Summary</span>
            )}
          </div>
          <FormattedNoteView note={currentNote} />
        </article>
      )}

      {!currentNote && !generating && (
        <div className="notes-empty">
          <p>
            Select a topic above and click <strong>Generate Notes</strong> to get AI study
            summaries.
          </p>
        </div>
      )}

      {history.length > 0 && (
        <section className="notes-history">
          <span className="notes-history-title">Session History</span>
          <div className="notes-history-list">
            {history.map((h) => (
              <button
                key={h.id}
                type="button"
                className="notes-history-chip"
                onClick={() => setCurrentNote(h)}
              >
                {h.topicName} ({h.timestamp})
              </button>
            ))}
          </div>
        </section>
      )}
    </main>
  );
}