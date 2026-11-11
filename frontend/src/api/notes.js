import { api } from "./client";

export async function fetchTopicNotes(subject, topicCode) {
  return api.post("/rag/summarize-notes", {
    subject,
    topic_code: topicCode,
  });
}