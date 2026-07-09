# Tutor Gojo 🎯

Your personal AI coding mentor, powered by Google Gemini.

## Features
- 💬 **Smart Chat** - Ask anything about coding and technology
- 📚 **Teaching Mode** - Gojo explains step-by-step, checks your understanding
- 📝 **Code Review** - Upload files for instant feedback
- 📋 **Copy Code** - One-click copy on all code blocks
- 🎨 **Anime Theme** - Dark purple aesthetic inspired by Satoru Gojo
- 💾 **Persistent History** - Your conversations are saved locally
- ⚙️ **Customizable** - Adjust teaching style and preferences

## Setup

### 1. Get a Gemini API Key
1. Go to [Google AI Studio](https://aistudio.google.com)
2. Create an API key (it's free)
3. Copy the key

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Run the App
```bash
python main.py
```

On first launch, you'll enter your API key and name. That's it!

## Building the Executable

To create a standalone `.exe` for Windows:

```bash
pip install pyinstaller
python build.py
```

The executable will be in `dist/TutorGojo.exe`.

## Project Structure
```
tutor_gojo/
├── main.py              # Main application
├── config.py            # Settings & API key management
├── database.py          # SQLite chat history & progress
├── gemini_client.py     # Gemini AI wrapper
├── requirements.txt     # Python dependencies
├── build.py            # PyInstaller build script
├── assets/             # Images and resources
└── data/               # Additional data files
```

## Tech Stack
- **UI**: CustomTkinter (modern, dark-themed widgets)
- **AI**: Google Gemini API
- **Database**: SQLite (local, no server needed)
- **Packaging**: PyInstaller

---
*"You're getting stronger, student." - Gojo*
