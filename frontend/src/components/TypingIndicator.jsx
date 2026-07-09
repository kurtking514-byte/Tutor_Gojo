import { Sparkles } from "lucide-react";

export default function TypingIndicator() {
  return (
    <div className="flex animate-fade-in-up gap-3">
      <div className="relative mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center">
        <span className="absolute inset-0 animate-pulse-glow rounded-full bg-accent/40 blur-md" />
        <div className="relative flex h-8 w-8 items-center justify-center rounded-full bg-accent text-white shadow-glow">
          <Sparkles size={15} />
        </div>
      </div>

      <div className="flex items-center gap-1.5 rounded-2xl rounded-tl-sm border border-hairline bg-elevated px-4 py-3.5">
        <span className="h-1.5 w-1.5 animate-bounce-dot rounded-full bg-accent-soft [animation-delay:-0.3s]" />
        <span className="h-1.5 w-1.5 animate-bounce-dot rounded-full bg-accent-soft [animation-delay:-0.15s]" />
        <span className="h-1.5 w-1.5 animate-bounce-dot rounded-full bg-accent-soft" />
      </div>
    </div>
  );
}
