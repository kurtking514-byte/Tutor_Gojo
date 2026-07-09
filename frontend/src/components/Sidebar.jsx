import { GraduationCap, MessageSquarePlus, Settings as SettingsIcon, X } from "lucide-react";

export default function Sidebar({
  sessions,
  isLoadingSessions,
  sessionsError,
  activeSessionId,
  onSelectSession,
  onNewSession,
  onOpenSettings,
  onOpenLearningDashboard,
  isOpen,
  onClose,
}) {
  return (
    <>
      {/* Mobile scrim */}
      {isOpen && (
        <div
          className="fixed inset-0 z-30 bg-black/60 md:hidden"
          onClick={onClose}
          aria-hidden="true"
        />
      )}

      <aside
        className={`fixed inset-y-0 left-0 z-40 flex w-72 shrink-0 flex-col border-r border-hairline bg-surface transition-transform duration-200 md:static md:translate-x-0 ${
          isOpen ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        <div className="flex items-center justify-between px-4 py-4">
          <div className="flex items-center gap-2">
            <span className="font-display text-lg font-semibold tracking-tight text-ink">
              悟 Tutor Gojo
            </span>
          </div>
          <button
            onClick={onClose}
            className="rounded p-1 text-ink-muted hover:bg-elevated hover:text-ink md:hidden"
            aria-label="Close sidebar"
          >
            <X size={18} />
          </button>
        </div>

        <div className="px-3">
          <button
            onClick={onNewSession}
            className="flex w-full items-center gap-2 rounded-lg border border-hairline bg-elevated px-3 py-2.5 text-sm font-medium text-ink transition-colors hover:border-accent/50 hover:bg-accent/10"
          >
            <MessageSquarePlus size={16} className="text-accent-soft" />
            New chat
          </button>
        </div>

        <div className="scrollbar-thin mt-4 flex-1 space-y-1 overflow-y-auto px-3">
          <p className="px-2 pb-1 font-display text-[11px] font-medium uppercase tracking-wider text-ink-muted">
            Recent
          </p>
          {isLoadingSessions && (
            <p className="px-2 py-2 text-sm text-ink-muted">Loading chats…</p>
          )}
          {!isLoadingSessions && sessionsError && (
            <p className="px-2 py-2 text-sm text-red-400">
              Couldn't load chats: {sessionsError}
            </p>
          )}
          {!isLoadingSessions && !sessionsError && sessions.map((session) => {
            const active = session.id === activeSessionId;
            return (
              <button
                key={session.id}
                onClick={() => onSelectSession(session.id)}
                className={`block w-full truncate rounded-lg px-3 py-2 text-left text-sm transition-colors ${
                  active
                    ? "bg-accent/15 text-ink"
                    : "text-ink-muted hover:bg-elevated hover:text-ink"
                }`}
              >
                {session.title || "New chat"}
              </button>
            );
          })}
        </div>

        <div className="border-t border-hairline px-3 py-3">
          <button
            onClick={onOpenLearningDashboard}
            className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm text-ink-muted transition-colors hover:bg-elevated hover:text-ink"
          >
            <GraduationCap size={16} />
            Learning Dashboard
          </button>
          <button
            onClick={onOpenSettings}
            className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm text-ink-muted transition-colors hover:bg-elevated hover:text-ink"
          >
            <SettingsIcon size={16} />
            Settings
          </button>
        </div>
      </aside>
    </>
  );
}
