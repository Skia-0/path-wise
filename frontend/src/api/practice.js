import { api } from "./client";

export function startPractice(subject) {
  return api.post("/practice/start", { subject, num_questions: 20 });
}

export function autosavePracticeAnswer({ sessionId, questionId, selectedOption }) {
  return api.post("/practice/autosave", {
    attempt_id: sessionId,
    session_type: "practice",
    question_id: questionId,
    selected_option: selectedOption,
  });
}

export function submitPractice({ sessionId, answers }) {
  return api.post("/practice/submit", { session_id: sessionId, answers });
}