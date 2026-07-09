import { useState } from "react";
import { X } from "lucide-react";
import Sidebar from "./components/Sidebar.jsx";
import ChatWindow from "./components/ChatWindow.jsx";
import Settings from "./components/Settings.jsx";
import LearningDashboard from "./components/LearningDashboard.jsx";
import { useChat } from "./hooks/UseChat.jsx";

export default function App() {
  const {
    sessions,
    activeSessionId,
    messages,
    isStreaming,
    isLoadingSessions,
    sessionsError,
    selectSession,
    createNewSession,
    sendMessage,
  } = useChat();

  const [isSidebarOpen, setSidebarOpen] = useState(false);
  const [isSettingsOpen, setSettingsOpen] = useState(false);
  const [isLearningDashboardOpen, setIsLearningDashboardOpen] = useState(false);

  const openLearningDashboard = () => setIsLearningDashboardOpen(true);
  const closeLearningDashboard = () => setIsLearningDashboardOpen(false);

  const activeSession = sessions.find((s) => s.id === activeSessionId);

  return (
    <div className="flex h-screen overflow-hidden bg-void">
      <Sidebar
        sessions={sessions}
        isLoadingSessions={isLoadingSessions}
        sessionsError={sessionsError}
        activeSessionId={activeSessionId}
        onSelectSession={(id) => {
          selectSession(id);
          setSidebarOpen(false);
        }}
        onNewSession={() => {
          createNewSession();
          setSidebarOpen(false);
        }}
        onOpenSettings={() => setSettingsOpen(true)}
        onOpenLearningDashboard={openLearningDashboard}
        isOpen={isSidebarOpen}
        onClose={() => setSidebarOpen(false)}
      />

      <ChatWindow
        messages={messages}
        isStreaming={isStreaming}
        onSend={sendMessage}
        onOpenSidebar={() => setSidebarOpen(true)}
        sessionTitle={activeSession?.title}
      />

      <Settings isOpen={isSettingsOpen} onClose={() => setSettingsOpen(false)} />

      {isLearningDashboardOpen && (
        <div className="fixed inset-0 z-50 flex justify-end">
          <div
            className="absolute inset-0 bg-black/60"
            onClick={closeLearningDashboard}
            aria-hidden="true"
          />

          <div className="relative flex h-full w-full max-w-3xl flex-col border-l border-hairline bg-surface animate-fade-in-up">
            <div className="flex items-center justify-between border-b border-hairline px-5 py-4">
              <h2 className="font-display text-base font-semibold text-ink">
                Learning Dashboard
              </h2>
              <button
                onClick={closeLearningDashboard}
                className="rounded p-1 text-ink-muted hover:bg-elevated hover:text-ink"
                aria-label="Close learning dashboard"
              >
                <X size={18} />
              </button>
            </div>

            <div className="flex-1 overflow-y-auto">
              <LearningDashboard />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
