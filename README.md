# Tutor Gojo

Tutor Gojo is an AI-powered programming tutor that helps you learn to code through interactive, streaming conversations. It's built with a React + Vite frontend and a FastAPI backend, powered by the Google Gemini API, with chat history stored in SQLite and long-term learning progress stored as Markdown-based memory.

---

## Features

- **AI tutoring chat** — ask programming questions and get clear, guided explanations
- **Real-time streaming responses** — answers stream in via Server-Sent Events (SSE) as they're generated
- **Persistent chat history** — conversations are saved and can be revisited
- **Learning memory** — Tutor Gojo remembers your previous learning progress across sessions
- **Markdown-based memory storage** — learning memory is stored in a simple, human-readable Markdown format
- **Anonymous browser-based sessions** — no login required; each browser only sees its own chat history
- **Mobile-responsive interface** — usable on both desktop and mobile
- **Google Gemini integration** — powered by Google's Gemini API
- **Learning Dashboard** — view a summary of your learning progress
- **Lesson Recommendations** — get suggested next topics based on your progress

---

## Project Structure

```
backend/
  - FastAPI API
  - Database
  - AI chat services
  - Memory system

frontend/
  - React UI
  - Chat interface
  - Sidebar
  - Dashboard
  - API client
```

---

## Tech Stack

**Frontend**
- React
- Vite

**Backend**
- FastAPI
- SQLite
- Google Gemini API

**Memory**
- Markdown-based storage

**Deployment**
- Render

---

## Local Installation

**Backend**
```bash
cd backend
pip install -r requirements.txt
python -m uvicorn api:app --reload
```

**Frontend**
```bash
cd frontend
npm install
npm run dev
```

---

## Deployment

- **Backend:** Render Web Service
- **Frontend:** Render Static Site

**Required environment variable:**
```
GEMINI_API_KEY
```

---

## Screenshots

_Coming soon._

---

## Roadmap

Planned for future releases:

- User authentication
- File uploads (PDF, code, documents)
- Automatic chat titles
- Multiple Gemini API key rotation
- Conversation export
- Better personalization
- Additional AI providers (future)

---

## License

MIT

---

## Contributing

Contributions are welcome! To contribute:

1. Fork the repository
2. Create a new branch for your change
3. Make your changes and test locally
4. Submit a pull request with a clear description of what you changed and why

For larger changes, please open an issue first to discuss what you'd like to change.

---

## Author

Author: (Your Name)
