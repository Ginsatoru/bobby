# Bobby

Local company AI assistant prototype. Python + FastAPI backend, Ollama for the model, plain HTML/CSS/JS frontend, SQLite for chat history. Runs entirely on your PC; no API keys or cloud services.

## Install (Windows 10/11)

1. **Python 3.10+**: install from https://www.python.org/downloads/ and tick **Add python.exe to PATH**.
2. **Ollama**: install from https://ollama.com/download, then leave it running (it starts in the system tray).
3. **Model**: open Command Prompt and run:
   ```
   ollama pull gemma3:4b
   ```
4. **Run Bobby**: double-click `run.bat`. First run creates a virtual environment, installs dependencies and copies `.env.example` to `.env`. The browser opens at http://127.0.0.1:8000.

The status pill (top right) shows the model and connection state. Click it to re-check.
Red = Ollama not running. Amber = model not installed.

## Configure

- `.env`: `OLLAMA_URL`, `OLLAMA_MODEL`, `OLLAMA_TIMEOUT`, `MAX_HISTORY_MESSAGES`. Restart `run.bat` after changing it.
- `app/prompts/system.txt`: Bobby's personality, company rules and style. **Edit the first line** with your company details. Changes apply on the next message, no restart needed.
- `app/prompts/email.txt`: extra instructions used in email-draft mode.

## Use

- **New chat**: ask Bobby anything. Replies stream in; **Stop** cancels (partial reply is kept).
- **New email draft**: paste the customer's message, optionally add context, send. Bobby writes a draft; ask for changes in follow-ups. Use **Copy** to take it. Nothing is ever sent automatically.
- **Clear chat** empties the current conversation. The × in the sidebar deletes a conversation.
- History is stored in `data/bobby.db`.

## Layout

```
app/
  main.py            FastAPI app, serves static files
  config.py          .env settings
  db.py              SQLite (conversations, messages)
  ollama_client.py   only module that talks to Ollama
  routes/            chat.py (chat + status), conversations.py
  services/
    prompts.py       builds system prompt + message list
    knowledge.py     RAG hook (returns nothing yet)
  prompts/           system.txt, email.txt
  static/            index.html, style.css, app.js
data/                SQLite file (created at runtime)
```

## Next phase: company knowledge (RAG)

Implement `retrieve()` in `app/services/knowledge.py` (index documents from `data/knowledge/`, return the top passages for a query). `services/prompts.py` already injects whatever it returns into the system prompt, so no other code needs to change.

## Not done yet

- RAG / document ingestion (hook only)
- Markdown rendering of replies (shown as plain text)
- Rename conversations, search history
- Settings screen (settings live in `.env` and the prompt files)
- Authentication / multi-user (intentionally out of scope)
# bobby
