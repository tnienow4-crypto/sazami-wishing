import discord
import os
import argparse
import asyncio
import datetime
import pytz
from main import query_gemini_raw, GUILD_ID, CHANNEL_ID
from dotenv import load_dotenv

# Load env
load_dotenv()

# Setup Arguments
parser = argparse.ArgumentParser(description='Daily Wish Bot')
parser.add_argument('--time', type=str, help='Time of day string (e.g. Morning, Evening). If not provided, auto-detected.')
parser.add_argument('--test', action='store_true', help='Run in test mode (prints to console, does not DM users)')
parser.add_argument('--target-id', type=str, help='Target specific User ID for testing (sends real DM only to this user)')
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

if args.target_id:
    # Sanitize target_id (remove quotes if passed by shell)
    args.target_id = args.target_id.strip('"').strip("'")

print(f"Starting Daily Wisher. Time: {TIME_OF_DAY}, Test Mode: {IS_TEST}, Target: {args.target_id}")

# Setup Discord
intents = discord.Intents.default()
intents.members = True
intents.message_content = True
client = discord.Client(intents=intents)


def chunk_mentions(members, *, prefix: str = "", suffix: str = "", max_len: int = 1900):
    """Yield strings of user mentions that fit within Discord's message limit.

    max_len is conservative to leave room for extra text.
    """
    chunk = []
    cur_len = len(prefix) + len(suffix)

    for m in members:
        mention = m.mention
        add_len = len(mention) + (1 if chunk else 0)
        if chunk and cur_len + add_len > max_len:
            yield (prefix + " ".join(chunk) + suffix)
            chunk = [mention]
            cur_len = len(prefix) + len(suffix) + len(mention)
        else:
            if chunk:
                cur_len += 1
            chunk.append(mention)
            cur_len += len(mention)

    if chunk:
        yield (prefix + " ".join(chunk) + suffix)

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

        # 1. Generate Wish Messages (ONCE for everyone)
        print("Generating daily wishes...")
        
        # Channel Wish
        channel_wish = await generate_with_retry(
            f"Write a cheerful {TIME_OF_DAY} wish for everyone in the server '{guild.name}'. Keep it in character (Sazami, anime girl). Use emojis.",
            f"Good {TIME_OF_DAY} everyone! Hope you have a great time! 💖"
        )
        
        # DM Wish (Generic but warm)
        dm_wish = await generate_with_retry(
            f"Write a warm, cute {TIME_OF_DAY} wish to send to a friend via DM. Keep it in character (Sazami). Do not mention specific names. Use emojis.",
            f"Hey! Just wanted to wish you a wonderful {TIME_OF_DAY}! Stay happy! ✨"
        )

        print(f"Generated DM Wish: {dm_wish[:50]}...")

        # 2. Prepare Image
        image_filename = f"good-{TIME_OF_DAY.lower()}.png"
        image_path = os.path.join("assets", image_filename)
        has_image = os.path.exists(image_path)
        
        if has_image:
            print(f"Found image for {TIME_OF_DAY}: {image_path}")
        else:
            print(f"WARNING: Image not found at {image_path}. Sending text only.")

        # 3. Send Channel Wish
        if channel:
            if IS_TEST:
                print(f"[TEST] Channel Message to #{channel.name}: {channel_wish} [Image: {image_filename if has_image else 'None'}]")
            else:
                try:
                    # Create fresh file object for channel
                    file_to_send = discord.File(image_path) if has_image else None
                    await channel.send(channel_wish, file=file_to_send)
                    print(f"Sent channel wish to #{channel.name}")
                except Exception as e:
                    print(f"Error sending channel wish: {e}")

        # 4. Broadcast DM Wish
        print(f"Fetching members...")
        if not guild.chunked:
            await guild.chunk()

        dm_failed_members = []
            
        for member in guild.members:
            if member.bot:
                continue

            # Target User Filter
            if args.target_id and str(member.id) != args.target_id:
                continue

            print(f"Processing {member.name} ({member.id})...")
            
            if IS_TEST:
                print(f"[TEST] DM to {member.name}: {dm_wish} [Image: {image_filename if has_image else 'None'}]")
            else:
                try:
                    # Create FRESH file object for each DM (stream is consumed)
                    file_to_send = discord.File(image_path) if has_image else None
                    await member.send(dm_wish, file=file_to_send)
                    print(f"Sent DM to {member.name}")
                except discord.Forbidden:
                    print(f"DM disabled for {member.name}. Will mention in summary message.")
                    dm_failed_members.append(member)
                except Exception as e:
                    print(f"Error sending to {member.name}: {e}")

            # Sleep briefly to avoid Discord rate limits (not Gemini anymore)
            await asyncio.sleep(1.5)

        # 5. Single summary message for members with DMs disabled
        if not IS_TEST and channel and dm_failed_members:
            allowed = discord.AllowedMentions(users=True, roles=False, everyone=False, replied_user=False)

            mentions_text = " ".join(m.mention for m in dm_failed_members)
            combined = f"{mentions_text}\n\n{dm_wish}".strip()

            # Prefer ONE message. If too long (large server), fall back to chunking mentions,
            # attaching the wish only to the final chunk.
            if len(combined) <= 2000:
                await channel.send(combined, allowed_mentions=allowed)
            else:
                mention_chunks = list(chunk_mentions(dm_failed_members, max_len=1900))
                for chunk_text in mention_chunks[:-1]:
                    await channel.send(chunk_text, allowed_mentions=allowed)
                await channel.send(f"{mention_chunks[-1]}\n\n{dm_wish}".strip(), allowed_mentions=allowed)

    except Exception as e:
        print(f"An error occurred during execution: {e}")
    finally:
        print("Done. Closing client.")
        await client.close()

if __name__ == "__main__":
    client.run(os.getenv("BOT_TOKEN"))
