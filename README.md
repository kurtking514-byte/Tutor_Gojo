# Tutor Gojo

Tutor Gojo is an AI tutoring application for learning to code. It pairs a **React + Vite** frontend with a **FastAPI** backend, uses **Google Gemini** as its primary LLM (with automatic failover to other providers), keeps a long-term **Markdown/Obsidian-style memory vault** of the student's progress, stores chat sessions in **SQLite**, and streams every reply to the browser in real time over **Server-Sent Events (SSE)**.

## Features

Only features that currently exist in the codebase are listed here.

- **AI tutoring chat** — a persona-driven coding mentor powered by Google Gemini
- **Streaming responses** — assistant replies stream to the UI chunk-by-chunk over SSE
- **Persistent chat history** — sessions and messages are stored in SQLite and reloaded on return visits
- **Long-term memory** — tracks student profile, topic mastery, strengths, misconceptions, coding-style traits, mistake patterns, journal entries, projects, assessments, and more across sessions
- **Markdown memory vault** — the memory system is backed by Markdown notes with YAML frontmatter (an Obsidian-style vault) rather than opaque database rows
- **Lesson recommendations** — a "what to learn next" recommendation derived from the student's memory profile
- **Learning dashboard** — an in-app view of progress, stats, and recommendations
- **Provider failover** — if Gemini fails, requests automatically retry against OpenRouter/Groq, with per-provider health tracking and cooldowns
- **Anonymous browser-based sessions** — no login required; a per-browser id (stored in `localStorage`) scopes each visitor's sessions and history so users only ever see their own chats
- **Mobile responsive UI** — a usable chat experience on phones, including a collapsible sidebar, scrollable code blocks, and a keyboard-friendly input bar

## Project Structure

```
backend/
frontend/
```

- **`backend/`** — the FastAPI application. Contains the API entrypoint (`api.py`), the SQLite chat/session layer (`database.py`), the multi-provider LLM router with failover (`llm_router.py`, `providers/`, `router/`), the Markdown/Obsidian-backed long-term memory system (`memory_engine/`, `obsidian_backend.py`), business logic services (`services/` — chat, history, memory, lesson recommendations), tutor persona/prompt content (`prompts/`), and an early-stage orchestration layer (`orchestrator/`).
- **`frontend/`** — the React + Vite single-page app. Contains UI components (`src/components/` — chat window, message bubbles, code blocks, sidebar, settings, learning dashboard), the chat state hook (`src/hooks/UseChat.jsx`), the backend API client (`src/api/client.js`), and global styles (`src/styles/`).

## Tech Stack

**Frontend:**
- React
- Vite

**Backend:**
- FastAPI
- SQLite
- Google Gemini API

**Memory:**
- Markdown Vault (Obsidian-style notes with YAML frontmatter)

**Deployment:**
- Render

## Installation (Local)

### Backend

```
cd backend
pip install -r requirements.txt
python -m uvicorn api:app --reload
```

### Frontend

```
cd frontend
npm install
npm run dev
```

## Deployment

**Backend:** Render Web Service, running the FastAPI app via `uvicorn`.

**Frontend:** Render Static Site, serving the Vite production build.

Required environment variables:

```
GEMINI_API_KEY
```

## Screenshots

(Add screenshots here)

## Roadmap

- User authentication
- File upload support
- Multiple Gemini API key rotation
- Better mobile UI
- Better chat titles
- Export conversations

## License

MIT

## Contributing

Contributions are welcome. Please open an issue to discuss any significant change before submitting a pull request, keep pull requests focused on a single change, and make sure the app still runs locally (both backend and frontend) before submitting.

## Author

Your Name Here
