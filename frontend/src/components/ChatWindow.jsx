import { useEffect, useRef } from "react";
import { Menu, Sparkles } from "lucide-react";
import MessageBubble from "./MessageBubble.jsx";
import TypingIndicator from "./TypingIndicator.jsx";
import InputBox from "./InputBox.jsx";

export default function ChatWindow({ messages, isStreaming, onSend, onOpenSidebar, sessionTitle }) {
  const scrollRef = useRef(null);

  // Smooth auto-scroll to the latest message whenever the list changes
  // (new message added, or a streamed message growing word-by-word).
  useEffect(() => {
    scrollRef.current?.scrollTo({
      top: scrollRef.current.scrollHeight,
      behavior: isStreaming ? "auto" : "smooth",
    });
  }, [messages, isStreaming]);

  const showTyping = isStreaming && messages[messages.length - 1]?.role === "user";

  return (
    <div className="flex h-full min-w-0 flex-1 flex-col">
      <header className="flex shrink-0 items-center gap-3 border-b border-hairline px-4 py-3 sm:px-6">
        <button
          onClick={onOpenSidebar}
          className="rounded p-1 text-ink-muted hover:bg-elevated hover:text-ink md:hidden"
          aria-label="Open sidebar"
        >
          <Menu size={20} />
        </button>
        <div className="flex items-center gap-2">
          <Sparkles size={16} className="text-accent-soft" />
          <h1 className="truncate font-display text-sm font-medium text-ink">
            {sessionTitle || "New chat"}
          </h1>
        </div>
      </header>

      <div ref={scrollRef} className="scrollbar-thin flex-1 overflow-y-auto scroll-smooth">
        <div className="mx-auto flex max-w-3xl flex-col gap-5 px-4 py-6 sm:px-6">
          {messages.length === 0 && !isStreaming && (
            <div className="flex flex-1 flex-col items-center justify-center py-24 text-center">
              <div className="relative mb-4 flex h-12 w-12 items-center justify-center">
                <span className="absolute inset-0 animate-pulse-glow rounded-full bg-accent/40 blur-lg" />
                <div className="relative flex h-12 w-12 items-center justify-center rounded-full bg-accent text-white shadow-glow">
                  <Sparkles size={20} />
                </div>
              </div>
              <p className="font-display text-base font-medium text-ink">Start a new chat</p>
              <p className="mt-1 max-w-xs text-sm text-ink-muted">
                Ask Tutor Gojo anything about code — concepts, debugging, or a full walkthrough.
              </p>
            </div>
          )}

          {messages.map((m) => (
            <MessageBubble key={m.id} role={m.role} content={m.content} timestamp={m.timestamp} />
          ))}

          {showTyping && <TypingIndicator />}
        </div>
      </div>

      <InputBox onSend={onSend} disabled={isStreaming} />
    </div>
  );
}
