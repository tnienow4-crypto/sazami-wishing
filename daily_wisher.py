import discord
import os
import argparse
import asyncio
import datetime
import inspect
import json
import random
import re
import pytz
from main import query_gemini_raw, GUILD_ID, CHANNEL_ID
from dotenv import load_dotenv

# Load env
load_dotenv()

# Setup Arguments
parser = argparse.ArgumentParser(description='Daily Wish Bot')
parser.add_argument('--time', type=str, help='Time of day string (e.g. Morning, Evening). If not provided, auto-detected.')
parser.add_argument('--test', action='store_true', help='Run in test mode (prints to console, does not DM users)')
args = parser.parse_args()

# Constants
IST = pytz.timezone('Asia/Kolkata')

def get_time_of_day():
    if args.time:
        return args.time
    
    # Auto-detect based on current IST time
    now = datetime.datetime.now(IST)
    hour = now.hour
    
    # 9am, 12pm, 4pm (16), 7pm (19), 11pm (23)
    if 5 <= hour < 11:
        return "Morning"
    elif 11 <= hour < 15:
        return "Noon" # or "Afternoon"
    elif 15 <= hour < 18:
        return "Afternoon"
    elif 18 <= hour < 21:
        return "Evening"
    else:
        return "Night"

TIME_OF_DAY = get_time_of_day().strip('"').strip("'")
IS_TEST = args.test

print(f"Starting Daily Wisher. Time: {TIME_OF_DAY}, Test Mode: {IS_TEST}")

# Setup Discord
intents = discord.Intents.default()
intents.members = True
intents.message_content = True
client = discord.Client(intents=intents)


_MENTION_RE = re.compile(r"<@&?\d+>|<@!?\d+>")


def strip_discord_mentions(text: str) -> str:
    if not text:
        return ""
    text = text.replace("@everyone", "everyone").replace("@here", "here")
    text = _MENTION_RE.sub("", text)
    # Avoid accidental pings from role/user-like strings
    text = text.replace("@", "")
    return text.strip()


async def fetch_guild_emojis_and_stickers(guild: discord.Guild):
    try:
        emojis = await guild.fetch_emojis()
    except Exception:
        emojis = list(getattr(guild, "emojis", []))

    try:
        stickers = await guild.fetch_stickers()
    except Exception:
        stickers = list(getattr(guild, "stickers", []))

    return emojis, stickers


def _extract_first_json_object(text: str) -> dict:
    if not text:
        return {}
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return {}
    candidate = text[start : end + 1]
    try:
        return json.loads(candidate)
    except Exception:
        return {}


async def pick_decorations_with_ai(*, guild: discord.Guild, time_of_day: str, wish_text: str, emojis, stickers):
    # Keep lists small to avoid prompt bloat
    emoji_names = [e.name for e in emojis[:25] if getattr(e, "name", None)]
    sticker_names = [s.name for s in stickers[:10] if getattr(s, "name", None)]

    # If nothing is available, we can still decorate with unicode.
    if not emoji_names and not sticker_names:
        return None, None

    prompt = (
        "Pick ONE custom emoji name and optionally ONE sticker name to match a daily server wish. "
        "You must choose only from the provided lists. If none fit, return null for that field. "
        "Never output @everyone, @here, or any mentions.\n\n"
        f"Time of day: {time_of_day}\n"
        f"Wish text: {wish_text}\n\n"
        f"Available custom emoji names: {emoji_names}\n"
        f"Available sticker names: {sticker_names}\n\n"
        "Return STRICT JSON ONLY in this shape: {\"emoji\": string|null, \"sticker\": string|null}"
    )

    raw = await asyncio.to_thread(query_gemini_raw, prompt)
    raw = strip_discord_mentions(raw)
    data = _extract_first_json_object(raw)

    emoji_pick = data.get("emoji") if isinstance(data, dict) else None
    sticker_pick = data.get("sticker") if isinstance(data, dict) else None

    emoji_obj = next((e for e in emojis if getattr(e, "name", None) == emoji_pick), None) if emoji_pick else None
    sticker_obj = next((s for s in stickers if getattr(s, "name", None) == sticker_pick), None) if sticker_pick else None
    return emoji_obj, sticker_obj


def fallback_unicode_emojis(time_of_day: str) -> list[str]:
    t = time_of_day.lower()
    if "morning" in t:
        return ["☀️", "🌸", "✨", "🍵", "🐾"]
    if "noon" in t or "afternoon" in t:
        return ["🌤️", "💛", "✨", "🍀", "🎐"]
    if "evening" in t:
        return ["🌙", "🌆", "✨", "🍵", "💫"]
    return ["🌙", "⭐", "✨", "🌌", "💤"]


def format_decorated_wish(*, time_of_day: str, wish_text: str, custom_emoji: str | None):
    wish_text = strip_discord_mentions(wish_text)

    base_pool = fallback_unicode_emojis(time_of_day)
    pool: list[str] = []
    if custom_emoji:
        pool.append(custom_emoji)
    pool.extend(e for e in base_pool if e not in pool)

    # Pick distinct emojis for decoration (avoid repeating the same emoji)
    picks = pool[:]
    random.shuffle(picks)

    # Ensure at least 3 distinct emojis; fall back gracefully if pool is small.
    e1 = picks[0] if len(picks) >= 1 else "✨"
    e2 = picks[1] if len(picks) >= 2 else ("🌸" if e1 != "🌸" else "💫")
    e3 = picks[2] if len(picks) >= 3 else ("💫" if e1 != "💫" and e2 != "💫" else "🍀")

    header = f"{e1} **Good {time_of_day}!** {e2}"
    footer = f"{e3} {e2} {e1}"
    return f"{header}\n{wish_text}\n{footer}".strip()

@client.event
async def on_ready():
    print(f'Logged in as {client.user}')
    
    try:
        guild = client.get_guild(GUILD_ID)
        if not guild:
            print(f"CRITICAL: Guild with ID {GUILD_ID} not found. Check bot invites and ID.")
            await client.close()
            return

        print(f"Processing guild: {guild.name} ({guild.id})")
        channel = guild.get_channel(CHANNEL_ID)
        
        if not channel:
            print(f"WARNING: Channel with ID {CHANNEL_ID} not found.")

        async def generate_with_retry(prompt, fallback):
            for i in range(3):
                msg = await asyncio.to_thread(query_gemini_raw, prompt)
                if "Gemini API Error" not in msg:
                    return msg
                print(f"Generation failed ({msg}). Retrying {i+1}/3...")
                await asyncio.sleep(5)
            return fallback

        # 1. Generate Wish Message (server-only)
        print("Generating daily server wish...")

        base_wish = await generate_with_retry(
            (
                f"Write a cheerful {TIME_OF_DAY} wish for a Discord server. "
                "Keep it friendly, short (1-2 paragraphs max), and decorative with emojis. "
                "Do NOT mention or tag any users or roles. "
                "Do NOT use @everyone or @here. "
                "Do NOT include any user names."
            ),
            f"Wishing you a lovely {TIME_OF_DAY}! Stay safe, stay strong, and have a beautiful day ahead! ✨"
        )
        base_wish = strip_discord_mentions(base_wish)

        # 2. Prepare Image
        image_filename = f"good-{TIME_OF_DAY.lower()}.png"
        image_path = os.path.join("assets", image_filename)
        has_image = os.path.exists(image_path)
        
        if has_image:
            print(f"Found image for {TIME_OF_DAY}: {image_path}")
        else:
            print(f"WARNING: Image not found at {image_path}. Sending text only.")

        # 3. Fetch decorations (custom emojis/stickers) and let AI pick
        emojis, stickers = await fetch_guild_emojis_and_stickers(guild)
        emoji_obj, sticker_obj = await pick_decorations_with_ai(
            guild=guild,
            time_of_day=TIME_OF_DAY,
            wish_text=base_wish,
            emojis=emojis,
            stickers=stickers,
        )
        decorated = format_decorated_wish(
            time_of_day=TIME_OF_DAY,
            wish_text=base_wish,
            custom_emoji=str(emoji_obj) if emoji_obj else None,
        )

        # 4. Send server wish (no DMs, no mentions, try to suppress notifications)
        if channel:
            if IS_TEST:
                print(
                    f"[TEST] Channel Message to #{channel.name}: {decorated} "
                    f"[Sticker: {getattr(sticker_obj, 'name', None)}] "
                    f"[Image: {image_filename if has_image else 'None'}]"
                )
            else:
                try:
                    send_kwargs = {
                        "content": decorated,
                        "allowed_mentions": discord.AllowedMentions.none(),
                    }

                    # Try to suppress notifications if the installed discord.py supports it.
                    try:
                        if "silent" in inspect.signature(channel.send).parameters:
                            send_kwargs["silent"] = True
                    except Exception:
                        pass

                    if has_image:
                        send_kwargs["file"] = discord.File(image_path)

                    # Stickers are optional and API/signature dependent.
                    if sticker_obj is not None:
                        try:
                            if "stickers" in inspect.signature(channel.send).parameters:
                                send_kwargs["stickers"] = [sticker_obj]
                        except Exception:
                            pass

                    await channel.send(**send_kwargs)
                    print(f"Sent server wish to #{channel.name}")
                except Exception as e:
                    print(f"Error sending server wish: {e}")

    except Exception as e:
        print(f"An error occurred during execution: {e}")
    finally:
        print("Done. Closing client.")
        await client.close()

if __name__ == "__main__":
    client.run(os.getenv("BOT_TOKEN"))
