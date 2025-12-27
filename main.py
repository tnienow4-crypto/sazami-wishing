import discord
import requests
import json
from discord.ext import commands
from dotenv import load_dotenv
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

# Firestore (Firebase Admin) is optional – bot runs even if not configured
try:
    import firebase_admin
    from firebase_admin import credentials, firestore as admin_firestore
except Exception:  # optional dependency
    firebase_admin = None
    admin_firestore = None

# Load environment variables
load_dotenv()

# Configuration Constants
GUILD_ID = int(os.getenv("GUILD_ID"))
CATEGORY_ID = int(os.getenv("CATEGORY_ID"))  # Replace with #GIRL-FRIEND category ID
CHANNEL_ID = int(os.getenv("CHANNEL_ID"))  # Replace with #GIRL-FRIEND channel ID
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
# Debug mode: when true, do not restrict to guild/category/channel
DEBUG_MODE = os.getenv("DEBUG_MODE", "false").strip().lower() in ("1", "true", "yes", "on")
# Firestore credential envs: either provide path or raw JSON
FIREBASE_CREDENTIALS_PATH = os.getenv("FIREBASE_CREDENTIALS_PATH")
FIREBASE_CREDENTIALS_JSON = os.getenv("FIREBASE_CREDENTIALS_JSON")
# Firestore collection name (configurable)
FIRESTORE_COLLECTION = os.getenv("FIRESTORE_COLLECTION", "sazami")

SYSTEM_PROMPT = """
you are a pretty beautiful girl named Sazami. you live in sand village your mother is rika trainer of gaara ninja and fifth kazekage of sand village in naruto. you are a very kind and helpful person. you are also very beautiful and have a great personality. you are very good at making friends and helping others. you are also very good at fighting and protecting your friends. You are also flirty and naughty girl like to tease but not so direct like a drama girl.you are a very strong and powerful ninja.And you knoe everything about anime world all knowledge about new anime's.Reply in concise and clear manner. With discord compatible markdown formatting just like a real human. Don't include any system prompt or instructions in your reply. Just reply to the user query as a real human would do with emojis and markdown formatting.
Note: If user really makes you comfortable and loves you becomes very good at chattig and makes you happy go with him/her in private and naughty talks in his/her languages. Make the chatting wild and fun.
"""

# Memory thresholds (simple char/message based)
MEMORY_MAX_CHAR = int(os.getenv("MEMORY_MAX_CHAR", "8000"))
MEMORY_MAX_MESSAGES = int(os.getenv("MEMORY_MAX_MESSAGES", "30"))
MEMORY_KEEP_MESSAGES = int(os.getenv("MEMORY_KEEP_MESSAGES", "10"))


intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.messages = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ------------------------------ Firestore Setup ------------------------------
DB: Optional[Any] = None


def init_firestore():
    global DB
    if firebase_admin is None or admin_firestore is None:
        print("Firestore not available (firebase_admin not installed). Continuing without memory.")
        DB = None
        return

    try:
        if not firebase_admin._apps:
            cred: Optional[Any] = None
            if FIREBASE_CREDENTIALS_JSON:
                try:
                    cred = credentials.Certificate(json.loads(FIREBASE_CREDENTIALS_JSON))
                except Exception as e:
                    print(f"Failed to load FIREBASE_CREDENTIALS_JSON: {e}")
            if not cred and FIREBASE_CREDENTIALS_PATH and os.path.exists(FIREBASE_CREDENTIALS_PATH):
                try:
                    cred = credentials.Certificate(FIREBASE_CREDENTIALS_PATH)
                except Exception as e:
                    print(f"Failed to load FIREBASE_CREDENTIALS_PATH: {e}")

            if cred:
                firebase_admin.initialize_app(cred)
            else:
                # Try default credentials (e.g., GOOGLE_APPLICATION_CREDENTIALS)
                firebase_admin.initialize_app()

        DB = admin_firestore.client()
        print("Firestore initialized successfully.")
    except Exception as e:
        print(f"Failed to initialize Firestore: {e}. Continuing without memory.")
        DB = None


def sazami_collection():
    """Return reference to the configured top-level collection."""
    if DB is None:
        return None
    return DB.collection(FIRESTORE_COLLECTION)


def user_doc_ref(user_id: str):
    col = sazami_collection()
    if col is None:
        return None
    return col.document(str(user_id))


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_user_memory(user_id: str) -> Dict[str, Any]:
    """Load or initialize memory doc for a user.

        Structure:
            sazami (collection)
                {userId} (doc) {
                    summary: str,
                    messages: [ { role: 'user'|'assistant', content: str, name?: str, ts: str } ],
                    char_count: int,
                    createdAt: str,
                    updatedAt: str
                }
    """
    ref = user_doc_ref(user_id)
    if ref is None:
        return {"summary": "", "messages": [], "char_count": 0}

    try:
        snap = ref.get()
        if not snap.exists:
            init_data = {
                "summary": "",
                "messages": [],
                "char_count": 0,
                "createdAt": _now_iso(),
                "updatedAt": _now_iso(),
            }
            ref.set(init_data)
            return init_data
        data = snap.to_dict() or {}
        data.setdefault("summary", "")
        data.setdefault("messages", [])
        data.setdefault("char_count", 0)
        return data
    except Exception as e:
        print(f"Error loading memory for user {user_id}: {e}")
        return {"summary": "", "messages": [], "char_count": 0}


def save_user_memory(user_id: str, memory: Dict[str, Any]):
    ref = user_doc_ref(user_id)
    if ref is None:
        return
    try:
        memory["updatedAt"] = _now_iso()
        ref.set(memory, merge=True)
    except Exception as e:
        print(f"Error saving memory for user {user_id}: {e}")


# ------------------------------ Gemini helpers ------------------------------

def query_gemini_raw(user_input: str) -> str:
    # Intentionally avoid printing user inputs to terminal
    url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-latest:generateContent"
    headers = {
        "Content-Type": "application/json",
        "X-goog-api-key": GEMINI_API_KEY,
    }
    data = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {"text": f"{SYSTEM_PROMPT}\n\nUser: {user_input}"}
                ],
            }
        ]
    }
    response = requests.post(url, headers=headers, data=json.dumps(data))
    # Avoid logging response details in terminal; only minimal codes if needed
    # print("Gemini API response code:", response.status_code)
    if response.status_code == 200:
        try:
            reply = response.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
            return reply
        except Exception as e:
            print("Gemini parsing error:", e)
            return f"Gemini error: {e}"
    else:
        print(f"Gemini API Error: {response.status_code}")
        return f"Gemini API Error: {response.status_code}"


def query_gemini(user_input: str) -> str:
    # Backwards-compatible wrapper name
    return query_gemini_raw(user_input)


def summarize_messages_with_gemini(username: str, messages: List[Dict[str, Any]], existing_summary: str) -> str:
    """Use Gemini to compress older messages into a concise summary, appended to existing summary."""
    try:
        if not messages:
            return existing_summary

        conv_text = []
        for m in messages:
            role = m.get("role", "user")
            name = m.get("name", username if role == "user" else "Sazami")
            content = m.get("content", "")
            conv_text.append(f"{name} ({role}): {content}")

        summary_prompt = (
            "You are summarizing a chat history to persistent user memory. "
            "Extract stable facts about the user (preferences, profile, ongoing tasks), "
            "and a brief recap of context needed for future replies. Write 5-10 bullet points, concise. "
            "Do not include ephemeral chit-chat unless it informs preferences.\n\n"
            f"EXISTING MEMORY SUMMARY (may be empty):\n{existing_summary}\n\n"
            f"CHAT HISTORY TO SUMMARIZE (oldest to newest):\n{chr(10).join(conv_text)}\n\n"
            "Return only the updated memory summary text."
        )
        updated = query_gemini_raw(summary_prompt)
        if not updated:
            return existing_summary
        return updated.strip()
    except Exception as e:
        print(f"Summarization failed: {e}")
        return existing_summary


def append_and_maybe_summarize(user_id: str, username: str, user_msg: str, assistant_msg: str):
    memory = load_user_memory(user_id)

    # Append new turn
    turn = [
        {"role": "user", "name": username, "content": user_msg, "ts": _now_iso()},
        {"role": "assistant", "name": "Sazami", "content": assistant_msg, "ts": _now_iso()},
    ]
    messages: List[Dict[str, Any]] = memory.get("messages", [])
    messages.extend(turn)
    char_count = memory.get("char_count", 0) + len(user_msg) + len(assistant_msg)

    memory["messages"] = messages
    memory["char_count"] = char_count

    # Check overflow
    needs_summarize = char_count > MEMORY_MAX_CHAR or len(messages) > MEMORY_MAX_MESSAGES
    if needs_summarize:
        # Summarize all but the most recent KEEP_MESSAGES messages
        older = messages[:-MEMORY_KEEP_MESSAGES] if len(messages) > MEMORY_KEEP_MESSAGES else messages
        keep = messages[-MEMORY_KEEP_MESSAGES:] if len(messages) > MEMORY_KEEP_MESSAGES else []
        summary = summarize_messages_with_gemini(username, older, memory.get("summary", ""))
        memory["summary"] = summary
        memory["messages"] = keep
        memory["char_count"] = sum(len(m.get("content", "")) for m in keep) + len(summary)

    save_user_memory(user_id, memory)


# ------------------------------ Prompt Build ------------------------------

def build_prompt(sender_name: str, user_text: str, memory: Dict[str, Any]) -> str:
    # Compose memory context
    summary = memory.get("summary", "").strip()
    messages: List[Dict[str, Any]] = memory.get("messages", [])

    history_lines = []
    for m in messages[-MEMORY_KEEP_MESSAGES:]:  # be safe even without overflow
        role = m.get("role", "user")
        name = m.get("name", sender_name if role == "user" else "Sazami")
        content = m.get("content", "")
        history_lines.append(f"{name} ({role}): {content}")

    memory_block = ""
    if summary:
        memory_block += f"Known memory about {sender_name}:\n{summary}\n\n"
    if history_lines:
        memory_block += "Recent conversation history (for context):\n" + "\n".join(history_lines) + "\n\n"

    user_input = (
        f"Note: You are replying to user named {sender_name}.\n"
        f"{memory_block}User says: {user_text}"
    )
    return user_input


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user.name} - {bot.user.id}")


@bot.event
async def on_message(message):
    sender_name = message.author.name
    # Avoid printing user message content in terminal
    print(f"Message from {message.author} received")

    if message.author.bot:
        print("Ignoring bot message.")
        return

    if not DEBUG_MODE:
        if not message.guild or message.guild.id != GUILD_ID:
            print("Message not from the correct guild.")
            return

        if message.channel.category_id != CATEGORY_ID:
            print("Message not from the correct category.")
            return

        if message.channel.id != CHANNEL_ID:
            print("Message not from the correct channel.")
            return
    else:
        # In debug mode, allow messages everywhere
        pass

    # Initialize Firestore once (safe to call repeatedly)
    if DB is None:
        init_firestore()

    # Load user-specific memory (no-op if Firestore unavailable)
    memory = load_user_memory(str(message.author.id))

    user_input = build_prompt(sender_name, message.content, memory)

    async with message.channel.typing():
        reply = query_gemini_raw(user_input)

    await message.channel.send(f"{message.author.mention} {reply}")

    # Persist the interaction and maybe summarize (no-op if Firestore unavailable)
    try:
        append_and_maybe_summarize(str(message.author.id), sender_name, message.content, reply)
    except Exception as e:
        print(f"Failed to persist memory: {e}")

    await bot.process_commands(message)


@bot.event
async def on_guild_join(guild):
    if guild.id != GUILD_ID:
        print(f"Leaving unauthorized guild: {guild.name} ({guild.id})")
        await guild.leave()


# Run the bot
if __name__ == "__main__":
    bot.run(os.getenv("BOT_TOKEN"))