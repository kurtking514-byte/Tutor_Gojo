/**
 * api/client.js
 *
 * Thin fetch wrapper matching the backend's FastAPI endpoints
 * (POST /chat, GET /history, POST /session, GET /progress).
 *
 * NOT WIRED UP YET. Nothing in the app currently imports this file -
 * hooks/useChat.jsx is running on local mock/simulated data for now so
 * the UI can be built and demoed standalone. When it's time to connect
 * the backend, swap the simulated streaming in useChat.jsx for
 * streamChat() below.
 */

const BASE_URL = "http://localhost:8000";

async function handleJson(res) {
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(`Request failed (${res.status}): ${body || res.statusText}`);
  }
  return res.json();
}

/** POST /session - create a new chat session. Returns { session_id }. */
export async function createSession({ title, topic } = {}) {
  const res = await fetch(`${BASE_URL}/session`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title: title ?? null, topic: topic ?? null }),
  });
  return handleJson(res);
}

/** GET /history - list all sessions. Returns { sessions: [...] }. */
export async function fetchSessions() {
  const res = await fetch(`${BASE_URL}/history`);
  return handleJson(res);
}

/** GET /history?session_id=... - get one session's messages. */
export async function fetchMessages(sessionId, limit = 50) {
  const params = new URLSearchParams({ session_id: sessionId, limit });
  const res = await fetch(`${BASE_URL}/history?${params.toString()}`);
  return handleJson(res);
}

/** GET /progress - learning progress + stats. */
export async function fetchProgress(topic) {
  const params = topic ? `?topic=${encodeURIComponent(topic)}` : "";
  const res = await fetch(`${BASE_URL}/progress${params}`);
  return handleJson(res);
}

/** GET /memory - full educational memory context (student profile, topic
 * mastery, strengths, misconceptions, journal, etc). Read-only. */
export async function fetchMemory() {
  const res = await fetch(`${BASE_URL}/memory`);
  return handleJson(res);
}

/** GET /lesson-recommendation - deterministic "what to learn next"
 * recommendation, derived from educational memory. Read-only. */
export async function fetchLessonRecommendation() {
  const res = await fetch(`${BASE_URL}/lesson-recommendation`);
  return handleJson(res);
}

/**
 * POST /chat - stream the assistant's reply via Server-Sent Events.
 *
 * The backend uses StreamingResponse with text/event-stream, which the
 * browser's EventSource API can't POST to directly, so this reads the
 * fetch body as a stream and parses SSE frames by hand.
 *
 * @param {string} sessionId
 * @param {string} message
 * @param {{ onChunk?: (text: string) => void, onDone?: () => void, onError?: (err: Error) => void }} handlers
 * @returns {() => void} an abort function to cancel the in-flight stream
 */
export function streamChat(sessionId, message, { onChunk, onDone, onError } = {}) {
  const controller = new AbortController();

  (async () => {
    try {
      const res = await fetch(`${BASE_URL}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId, message }),
        signal: controller.signal,
      });

      if (!res.ok || !res.body) {
        throw new Error(`Chat request failed (${res.status})`);
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      // Tracks whether the backend sent an explicit "event: done" frame.
      // If the connection closes cleanly without one (e.g. backend crash after
      // sending chunks), the fallback below ensures onDone still fires so
      // UseChat.jsx can reset isStreaming and unblock the input.
      let doneSignaled = false;

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const events = buffer.split("\n\n");
        buffer = events.pop(); // last chunk may be incomplete, keep it buffered

        for (const rawEvent of events) {
          const lines = rawEvent.split("\n");
          const eventType = lines.find((l) => l.startsWith("event:"))?.slice(6).trim();
          const dataLines = lines
            .filter((l) => l.startsWith("data:"))
            .map((l) => l.slice(5).trimStart());
          const data = dataLines.join("\n");

          if (eventType === "done") {
            doneSignaled = true;
            onDone?.();
          } else if (eventType === "error") {
            onError?.(new Error(data));
          } else if (data) {
            onChunk?.(data);
          }
        }
      }

      // Fallback: if the reader exhausted without a done event, signal completion
      // now so callers are never left in a permanently streaming state.
      if (!doneSignaled) onDone?.();
    } catch (err) {
      if (err.name !== "AbortError") {
        onError?.(err);
      }
    }
  })();

  return () => controller.abort();
}
