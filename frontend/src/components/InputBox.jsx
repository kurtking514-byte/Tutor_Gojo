import { useRef, useState } from "react";
import { ArrowUp, Paperclip } from "lucide-react";

export default function InputBox({ onSend, disabled }) {
  const [value, setValue] = useState("");
  const textareaRef = useRef(null);

  // Placeholder only - file attachment isn't implemented yet. Wire this up
  // alongside backend support for uploads (e.g. code review file upload).
  const handleAttachClick = () => {
    console.info("Attachment button clicked - not implemented yet.");
  };

  const resize = () => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  };

  const handleChange = (e) => {
    setValue(e.target.value);
    resize();
  };

  const handleSubmit = () => {
    if (!value.trim() || disabled) return;
    onSend(value);
    setValue("");
    requestAnimationFrame(resize);
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  return (
    <div className="border-t border-hairline bg-void px-4 py-4 sm:px-6">
      <div className="mx-auto flex max-w-3xl items-end gap-2 rounded-2xl border border-hairline bg-surface px-3 py-2 focus-within:border-accent/60">
        <button
          onClick={handleAttachClick}
          disabled={disabled}
          aria-label="Attach a file"
          title="Attach a file (coming soon)"
          className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-ink-muted transition-colors hover:bg-elevated hover:text-ink disabled:opacity-30"
        >
          <Paperclip size={16} />
        </button>
        <textarea
          ref={textareaRef}
          value={value}
          onChange={handleChange}
          onKeyDown={handleKeyDown}
          rows={1}
          placeholder={disabled ? "Gojo is replying..." : "Ask Tutor Gojo anything about code..."}
          disabled={disabled}
          className="max-h-40 flex-1 resize-none bg-transparent py-1.5 text-[15px] text-ink placeholder:text-ink-muted focus:outline-none disabled:opacity-60"
        />
        <button
          onClick={handleSubmit}
          disabled={disabled || !value.trim()}
          aria-label="Send message"
          className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-accent text-white transition-opacity enabled:hover:bg-accent-soft disabled:opacity-30"
        >
          <ArrowUp size={16} />
        </button>
      </div>
      <p className="mx-auto mt-2 max-w-3xl text-center text-[11px] text-ink-muted">
        Tutor Gojo can make mistakes. Double-check anything that really matters.
      </p>
    </div>
  );
}
