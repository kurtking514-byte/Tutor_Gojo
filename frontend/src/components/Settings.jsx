import { useState } from "react";
import { X } from "lucide-react";

const LEVELS = ["beginner", "intermediate", "advanced"];
const INTENSITIES = [
  { value: "patient", label: "Patient" },
  { value: "accelerated", label: "Accelerated" },
];
const MODELS = ["gemini-2.5-flash", "gemini-2.5-pro"];

export default function Settings({ isOpen, onClose }) {
  // Local-only state for now - this mirrors config.py's DEFAULTS shape so
  // wiring it to GET/PATCH settings endpoints later is a straight swap.
  const [level, setLevel] = useState("beginner");
  const [intensity, setIntensity] = useState("patient");
  const [model, setModel] = useState("gemini-2.5-flash");

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div className="absolute inset-0 bg-black/60" onClick={onClose} aria-hidden="true" />

      <div className="relative flex h-full w-full max-w-sm flex-col border-l border-hairline bg-surface animate-fade-in-up">
        <div className="flex items-center justify-between border-b border-hairline px-5 py-4">
          <h2 className="font-display text-base font-semibold text-ink">Settings</h2>
          <button
            onClick={onClose}
            className="rounded p-1 text-ink-muted hover:bg-elevated hover:text-ink"
            aria-label="Close settings"
          >
            <X size={18} />
          </button>
        </div>

        <div className="scrollbar-thin flex-1 space-y-6 overflow-y-auto px-5 py-5">
          <fieldset>
            <legend className="mb-2 font-display text-[11px] font-medium uppercase tracking-wider text-ink-muted">
              Student level
            </legend>
            <div className="flex gap-2">
              {LEVELS.map((l) => (
                <button
                  key={l}
                  onClick={() => setLevel(l)}
                  className={`flex-1 rounded-lg border px-3 py-2 text-sm capitalize transition-colors ${
                    level === l
                      ? "border-accent bg-accent/15 text-ink"
                      : "border-hairline text-ink-muted hover:bg-elevated"
                  }`}
                >
                  {l}
                </button>
              ))}
            </div>
          </fieldset>

          <fieldset>
            <legend className="mb-2 font-display text-[11px] font-medium uppercase tracking-wider text-ink-muted">
              Teaching intensity
            </legend>
            <div className="flex gap-2">
              {INTENSITIES.map((opt) => (
                <button
                  key={opt.value}
                  onClick={() => setIntensity(opt.value)}
                  className={`flex-1 rounded-lg border px-3 py-2 text-sm transition-colors ${
                    intensity === opt.value
                      ? "border-accent bg-accent/15 text-ink"
                      : "border-hairline text-ink-muted hover:bg-elevated"
                  }`}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          </fieldset>

          <fieldset>
            <legend className="mb-2 font-display text-[11px] font-medium uppercase tracking-wider text-ink-muted">
              Model
            </legend>
            <select
              value={model}
              onChange={(e) => setModel(e.target.value)}
              className="w-full rounded-lg border border-hairline bg-elevated px-3 py-2 text-sm text-ink focus:border-accent/60 focus:outline-none"
            >
              {MODELS.map((m) => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))}
            </select>
          </fieldset>
        </div>

        <div className="border-t border-hairline px-5 py-4">
          <p className="text-xs text-ink-muted">
            These settings aren't connected to the backend yet - they'll map to{" "}
            <code className="rounded bg-elevated px-1 py-0.5 font-mono">config.py</code>'s
            level / teaching_intensity / model fields once wired up.
          </p>
        </div>
      </div>
    </div>
  );
}
