import { api } from "./client";

export function startDiagnostic(subject) {
  return api.post("/diagnostic/start", { subject });
}

export function autosaveDiagnosticAnswer({ attemptId, questionId, selectedOption }) {
  return api.post("/diagnostic/autosave", {
    attempt_id: attemptId,
    question_id: questionId,
    selected_option: selectedOption,
    session_type: "diagnostic",
  });
}

export function submitDiagnostic({ attemptId, answers }) {
  return api.post("/diagnostic/submit", {
    attempt_id: attemptId,
    answers,
  });
}