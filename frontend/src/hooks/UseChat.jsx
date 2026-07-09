import { useCallback, useEffect, useRef, useState } from "react";
import { streamChat, createSession, fetchSessions, fetchMessages } from "../api/client.js";

/**
 * useChat.jsx
 *
 * Owns chat state: sessions, the active session's messages, and whether
 * the assistant is currently "typing". sendMessage() streams real replies
 * from the FastAPI backend via streamChat() in "../api/client.js".
 *
 * Sessions are now loaded from the backend (GET /history via
 * fetchSessions()) instead of local mock data. backendSessionIdsRef maps
 * local session id -> backend session id; for sessions loaded from the
 * backend this is an identity mapping (the id already *is* the backend
 * session id). For sessions created locally via createNewSession(), the
 * mapping is filled in lazily the first time a message is sent, via
 * POST /session (createSession()) - unchanged from before.
 */

// localStorage key used to remember the active session across reloads.
const ACTIVE_SESSION_STORAGE_KEY = "tutorgojo:activeSessionId";

export function useChat() {
  const [sessions, setSessions] = useState([]);
  const [activeSessionId, setActiveSessionId] = useState(null);
  const [messagesBySession, setMessagesBySession] = useState({});
  const [isStreaming, setIsStreaming] = useState(false);
  const [isLoadingSessions, setIsLoadingSessions] = useState(true);
  const [sessionsError, setSessionsError] = useState(null);

  const abortStreamRef = useRef(null);
  const backendSessionIdsRef = useRef({});
  // Tracks which sessions' messages have already been fetched (or are
  // local-only and don't need fetching), so switching back to a session
  // doesn't repeatedly hit GET /history.
  const loadedMessagesRef = useRef(new Set());

  const messages = messagesBySession[activeSessionId] ?? [];

  const appendMessage = useCallback((sessionId, message) => {
    setMessagesBySession((prev) => ({
      ...prev,
      [sessionId]: [...(prev[sessionId] ?? []), message],
    }));
  }, []);

  const updateLastMessage = useCallback((sessionId, updater) => {
    setMessagesBySession((prev) => {
      const existing = prev[sessionId] ?? [];
      if (existing.length === 0) return prev;
      const next = [...existing];
      next[next.length - 1] = updater(next[next.length - 1]);
      return { ...prev, [sessionId]: next };
    });
  }, []);

  // On mount: load sessions from the backend, then restore whichever
  // session was last active (if it still exists) or fall back to the
  // first session in the list.
  useEffect(() => {
    let cancelled = false;

    (async () => {
      try {
        const data = await fetchSessions();
        if (cancelled) return;

        const mapped = (data.sessions ?? []).map((s) => ({
          id: s.session_id,
          title: s.title,
          topic: s.topic,
        }));

        // Backend-loaded sessions already have real backend ids - no
        // lazy POST /session needed for these.
        mapped.forEach((s) => {
          backendSessionIdsRef.current[s.id] = s.id;
        });

        setSessions(mapped);
        setSessionsError(null);

        const storedId = localStorage.getItem(ACTIVE_SESSION_STORAGE_KEY);
        const initialId =
          storedId && mapped.some((s) => s.id === storedId)
            ? storedId
            : mapped[0]?.id ?? null;

        setActiveSessionId(initialId);
      } catch (err) {
        console.error("Failed to load sessions:", err);
        if (!cancelled) setSessionsError(err.message || "Failed to load sessions.");
      } finally {
        if (!cancelled) setIsLoadingSessions(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, []);

  // Persist the active session id so a reload can restore it.
  useEffect(() => {
    if (activeSessionId) {
      localStorage.setItem(ACTIVE_SESSION_STORAGE_KEY, activeSessionId);
    }
  }, [activeSessionId]);

  // Load messages for the active session the first time it's selected.
  // Already-loaded sessions (including freshly created local ones) are
  // skipped so switching back and forth doesn't refetch.
  useEffect(() => {
    if (!activeSessionId) return;
    if (loadedMessagesRef.current.has(activeSessionId)) return;

    let cancelled = false;
    let settled = false;
    loadedMessagesRef.current.add(activeSessionId);

    (async () => {
      try {
        const data = await fetchMessages(activeSessionId);
        if (cancelled) return;

        const mapped = (data.messages ?? []).map((m, i) => ({
          id: m.id ?? `${activeSessionId}-${i}`,
          role: m.role,
          content: m.content ?? m.message ?? "",
          timestamp: m.timestamp ?? m.created_at ?? null,
        }));

        // Merge rather than overwrite: if the user sent a message while this
        // fetch was in flight (e.g. slow cold-start response), that
        // optimistically-appended message won't be in `mapped` yet (it
        // isn't persisted on the backend). Overwriting outright would
        // silently discard it. Fetched history ids are backend ids and
        // never collide with locally-generated `u-...`/`a-...` ids, so
        // any local-only entries are simply kept after the fetched ones.
        setMessagesBySession((prev) => {
          const local = prev[activeSessionId] ?? [];
          const fetchedIds = new Set(mapped.map((m) => m.id));
          const localOnly = local.filter((m) => !fetchedIds.has(m.id));
          return { ...prev, [activeSessionId]: [...mapped, ...localOnly] };
        });
        settled = true;
      } catch (err) {
        console.error("Failed to load messages:", err);
        // Genuine fetch failure (not a cancellation) - still counts as
        // settled so we don't refetch-loop; the session just stays
        // empty in the UI until the next full reload.
        if (!cancelled) settled = true;
      }
    })();

    return () => {
      cancelled = true;
      // If the fetch never actually completed (the user navigated away
      // before it resolved), un-mark this session so returning to it
      // later retries the fetch instead of silently staying empty.
      if (!settled) loadedMessagesRef.current.delete(activeSessionId);
    };
  }, [activeSessionId]);

  const selectSession = useCallback((sessionId) => {
    setActiveSessionId(sessionId);
  }, []);

  const createNewSession = useCallback(() => {
    const id = `s${Date.now()}`;
    const session = { id, title: "New chat", topic: null };
    // Local-only session with no messages yet - nothing to fetch.
    loadedMessagesRef.current.add(id);
    setSessions((prev) => [session, ...prev]);
    setMessagesBySession((prev) => ({ ...prev, [id]: [] }));
    setActiveSessionId(id);
  }, []);

  const sendMessage = useCallback(
    (text) => {
      const trimmed = text.trim();
      if (!trimmed || isStreaming) return;

      const sessionId = activeSessionId;
      if (!sessionId) return;

      appendMessage(sessionId, {
        id: `u-${Date.now()}`,
        role: "user",
        content: trimmed,
        timestamp: new Date().toISOString(),
      });

      setIsStreaming(true);
      // The assistant bubble is NOT pre-created here. It is created on the
      // first onChunk so the typing indicator shows alone while waiting —
      // no empty bubble appears before real content exists.

      (async () => {
        // Tracks whether the assistant bubble has been appended yet.
        // Shared by onChunk (create vs. update) and error handlers so
        // neither ever operates on the wrong message.
        let assistantMessageCreated = false;

        // Creates the bubble on first error, or writes into it if it already
        // exists — covers both onError and the outer catch.
        const showError = (err) => {
          if (!assistantMessageCreated) {
            assistantMessageCreated = true;
            appendMessage(sessionId, {
              id: `a-${Date.now()}`,
              role: "assistant",
              content: `⚠️ ${err.message}`,
              timestamp: new Date().toISOString(),
            });
          } else {
            updateLastMessage(sessionId, (msg) => ({
              ...msg,
              content: msg.content || `⚠️ ${err.message}`,
            }));
          }
          setIsStreaming(false);
          abortStreamRef.current = null;
        };

        try {
          // For backend-loaded sessions the mapping is identity; for new local
          // sessions this calls POST /session once and caches the result.
          let backendSessionId = backendSessionIdsRef.current[sessionId];
          if (!backendSessionId) {
            const session = sessions.find((s) => s.id === sessionId);
            const { session_id } = await createSession({
              title: session?.title,
              topic: session?.topic,
            });
            backendSessionId = session_id;
            backendSessionIdsRef.current[sessionId] = backendSessionId;
          }

          abortStreamRef.current = streamChat(backendSessionId, trimmed, {
            onChunk: (chunk) => {
              if (!assistantMessageCreated) {
                // First chunk: create the bubble with real content.
                assistantMessageCreated = true;
                appendMessage(sessionId, {
                  id: `a-${Date.now()}`,
                  role: "assistant",
                  content: chunk,
                  timestamp: new Date().toISOString(),
                });
              } else {
                // Subsequent chunks: append to the existing bubble.
                updateLastMessage(sessionId, (msg) => ({
                  ...msg,
                  content: msg.content + chunk,
                }));
              }
            },
            onDone: () => {
              setIsStreaming(false);
              abortStreamRef.current = null;
            },
            onError: showError,
          });
        } catch (err) {
          showError(err);
        }
      })();
    },
    [activeSessionId, appendMessage, isStreaming, sessions, updateLastMessage]
  );

  return {
    sessions,
    activeSessionId,
    messages,
    isStreaming,
    isLoadingSessions,
    sessionsError,
    selectSession,
    createNewSession,
    sendMessage,
  };
}
