import { useState } from "react";
import { api, ApiError } from "../api/client";
import "./sus-modal.css";

const SUS_QUESTIONS = [
  "I think that I would like to use Path-Wise frequently.",
  "I found Path-Wise unnecessarily complex.",
  "I thought Path-Wise was easy to use.",
  "I think that I would need the support of a technical person to be able to use Path-Wise.",
  "I found the various functions in Path-Wise were well integrated.",
  "I thought there was too much inconsistency in Path-Wise.",
  "I would imagine that most Ghanaian SHS students would learn to use Path-Wise very quickly.",
  "I found Path-Wise very cumbersome to use.",
  "I felt very confident using Path-Wise.",
  "I needed to learn a lot of things before I could get going with Path-Wise.",
];

const LIKERT_OPTIONS = [
  { value: 1, label: "Strongly Disagree" },
  { value: 2, label: "Disagree" },
  { value: 3, label: "Neutral" },
  { value: 4, label: "Agree" },
  { value: 5, label: "Strongly Agree" },
];

export default function SusModal({ isOpen, onClose, onSubmitted }) {
  const [answers, setAnswers] = useState({});
  const [feedback, setFeedback] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [scoreResult, setScoreResult] = useState(null);

  if (!isOpen) return null;

  function handleSelect(questionIndex, value) {
    setAnswers((prev) => ({
      ...prev,
      [`q${questionIndex + 1}`]: value,
    }));
  }

  const answeredCount = Object.keys(answers).length;
  const isComplete = answeredCount === 10;

  async function handleSubmit(e) {
    e.preventDefault();
    if (!isComplete) {
      setError("Please answer all 10 usability questions before submitting.");
      return;
    }

    setSubmitting(true);
    setError("");

    const payload = {
      ...answers,
      feedback: feedback.trim(),
    };

    try {
      const res = await api.post("/evaluation/sus", payload);
      setScoreResult(res.sus_score);
      if (typeof onSubmitted === "function") {
        onSubmitted(res.sus_score);
      }
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : "Could not submit survey. Please try again."
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="sus-backdrop" role="dialog" aria-modal="true">
      <div className="sus-card">
        <header className="sus-header">
          <h2>Path-Wise Usability Evaluation</h2>
          <p>Standard 10-Item System Usability Scale (SUS)</p>
          <button
            type="button"
            className="sus-close-btn"
            onClick={onClose}
            aria-label="Close survey"
          >
            &times;
          </button>
        </header>

        {scoreResult !== null ? (
          <div className="sus-success">
            <div className="sus-score-badge">{scoreResult} / 100</div>
            <h3>Thank you for evaluating Path-Wise!</h3>
            <p>
              Your usability score of <strong>{scoreResult}</strong> has been
              recorded for our Chapter 5 evaluation data.
            </p>
            <button
              type="button"
              className="btn-primary"
              onClick={onClose}
              style={{ marginTop: "16px" }}
            >
              Back to App
            </button>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="sus-form">
            <div className="sus-progress">
              <span>
                Progress: {answeredCount} / 10 questions answered
              </span>
              <div
                className="sus-progress-bar"
                style={{ width: `${(answeredCount / 10) * 100}%` }}
              />
            </div>

            <div className="sus-questions-list">
              {SUS_QUESTIONS.map((qText, idx) => {
                const qKey = `q${idx + 1}`;
                const currentVal = answers[qKey];

                return (
                  <div key={qKey} className="sus-question-item">
                    <p className="sus-question-text">
                      <span className="sus-q-num">{idx + 1}.</span> {qText}
                    </p>
                    <div className="sus-likert-group">
                      {LIKERT_OPTIONS.map((opt) => (
                        <label
                          key={opt.value}
                          className={`sus-likert-label ${
                            currentVal === opt.value ? "selected" : ""
                          }`}
                        >
                          <input
                            type="radio"
                            name={qKey}
                            value={opt.value}
                            checked={currentVal === opt.value}
                            onChange={() => handleSelect(idx, opt.value)}
                          />
                          <span className="sus-val">{opt.value}</span>
                          <span className="sus-lbl">{opt.label}</span>
                        </label>
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>

            <div className="sus-feedback-group">
              <label htmlFor="sus-feedback-input">
                Additional Comments or Suggestions (Optional):
              </label>
              <textarea
                id="sus-feedback-input"
                rows={3}
                placeholder="Share any thoughts on your learning experience or improvement suggestions..."
                value={feedback}
                onChange={(e) => setFeedback(e.target.value)}
              />
            </div>

            {error && <p className="alert-error">{error}</p>}

            <div className="sus-actions">
              <button
                type="button"
                className="btn-ghost"
                onClick={onClose}
                disabled={submitting}
              >
                Cancel
              </button>
              <button
                type="submit"
                className="btn-primary"
                disabled={!isComplete || submitting}
              >
                {submitting ? "Submitting..." : "Submit Evaluation"}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}