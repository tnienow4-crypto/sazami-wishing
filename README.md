# SazamiBot with Firestore-backed Memory

This bot replies using Gemini and stores per-user memory in Firebase Firestore under a configurable collection (default `sazami`).

## Features
- Per-user memory: `sazami/{userId}` with `summary`, `messages`, `char_count`.
- Auto summarization: when memory exceeds thresholds, older messages are summarized and retained as `summary` while recent messages are kept.
- Graceful fallback: if Firestore isn't configured, the bot still runs without memory.

## Setup
1. Prerequisites
   - Python 3.10+
   - A Discord bot token
   - Google AI Studio API key for Gemini (`GEMINI_API_KEY`)
   - Firebase project and a service account key for Firestore

2. Install dependencies
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

3. Configure environment
Create a `.env` file alongside `main.py` with:
```
BOT_TOKEN=your_discord_bot_token
GUILD_ID=1234567890
CATEGORY_ID=1234567890
CHANNEL_ID=1234567890
GEMINI_API_KEY=your_gemini_api_key
# Optional: allow the bot to respond in all servers/channels for local debugging
DEBUG_MODE=true
# Either of the following to authenticate to Firestore
FIREBASE_CREDENTIALS_PATH=C:\path\to\service-account.json
# Or embed the JSON (single line JSON string)
# FIREBASE_CREDENTIALS_JSON={"type":"service_account", ...}

# Optional memory tuning
MEMORY_MAX_CHAR=8000
MEMORY_MAX_MESSAGES=30
MEMORY_KEEP_MESSAGES=10

# Optional: Firestore collection name (default: sazami)
FIRESTORE_COLLECTION=sazami
```

4. Run the bot
```powershell
.\.venv\Scripts\Activate.ps1
python .\main.py
```

## Firestore Structure
- Collection: `{FIRESTORE_COLLECTION}` (default: `sazami`)
  - Document: `{userId}`
    - `summary`: string (persistent memory)
    - `messages`: array of { `role`, `name`, `content`, `ts` }
    - `char_count`: integer
    - `createdAt`, `updatedAt`: ISO timestamps

## Notes
- The bot only responds in the configured guild, category, and channel.
- If Firestore isn't available (no credentials or package missing), memory features are disabled automatically.
