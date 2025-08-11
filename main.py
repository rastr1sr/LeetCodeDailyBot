import discord
import aiohttp
import asyncio
import os
import logging
from dotenv import load_dotenv
from dataclasses import dataclass
from typing import Optional, Dict, Any

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
try:
    CHANNEL_ID = int(os.getenv("DISCORD_CHANNEL_ID", "0"))
except ValueError:
    logging.error("Invalid DISCORD_CHANNEL_ID. Please set a valid integer ID.")
    exit(1)

if not TOKEN:
    logging.error("DISCORD_TOKEN not found in environment variables.")
    exit(1)
if not CHANNEL_ID:
    logging.error("DISCORD_CHANNEL_ID not found or is zero.")
    exit(1)

LEETCODE_GRAPHQL_URL = "https://leetcode.com/graphql"
LEETCODE_BASE_URL = "https://leetcode.com"

DIFFICULTY_COLORS = {
    "Easy": discord.Color.green(),
    "Medium": discord.Color.gold(),
    "Hard": discord.Color.red(),
    "Unknown": discord.Color.dark_grey()
}

DIFFICULTY_EMOJIS = {
    "Easy": "🟢",
    "Medium": "🟡",
    "Hard": "🔴",
    "Unknown": "⚪"
}

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger('LeetCodeCronBot')

@dataclass
class LeetCodeProblem:
    id: str
    title: str
    link: str
    difficulty: str
    date: str

class LeetCodeCronBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        super().__init__(intents=intents)
        self._http_session: Optional[aiohttp.ClientSession] = None
        self.bg_task: Optional[asyncio.Task] = None

    async def setup_hook(self):
        logger.info("Setting up bot resources...")
        self._http_session = aiohttp.ClientSession(
            headers={"User-Agent": "DiscordBot/LeetCodeDaily (Python/aiohttp)"}
        )
        self.bg_task = self.loop.create_task(self.post_and_exit())

    async def on_ready(self):
        logger.info(f'Logged in as {self.user.name} ({self.user.id})')

    async def close(self):
        logger.info("Closing bot and cleaning up resources...")
        if self._http_session and not self._http_session.closed:
            await self._http_session.close()
            logger.info("aiohttp session closed.")
        await super().close()
        logger.info("Discord client closed.")

    async def post_and_exit(self):
        await self.wait_until_ready()

        target_channel: Optional[discord.TextChannel] = None
        try:
            target_channel = self.get_channel(CHANNEL_ID)
            if not isinstance(target_channel, discord.TextChannel):
                logger.error(f"Channel ID {CHANNEL_ID} does not correspond to a valid text channel.")
                return

            logger.info("Fetching daily LeetCode problem...")
            problem = await self.get_daily_problem()
            if not problem:
                logger.error("Failed to fetch daily problem details.")
                try:
                     await target_channel.send("❌ Failed to fetch the LeetCode daily challenge today.")
                except discord.Forbidden:
                     logger.error(f"Missing permissions to send status message in channel {CHANNEL_ID}.")
                except discord.HTTPException as e:
                     logger.error(f"Discord API error sending status message: {e.status} - {e.text}")
                return

            logger.info(f"Successfully fetched problem: {problem.id}. {problem.title}")

            embed = self.create_problem_embed(problem)
            thread_title = self.format_thread_title(problem)

            logger.info(f"Posting problem to channel #{target_channel.name} ({target_channel.id})")
            try:
                message = await target_channel.send(embed=embed)
                await message.create_thread(name=thread_title, auto_archive_duration=10080)
                logger.info(f"Successfully posted problem and created thread: '{thread_title}'")
            except discord.Forbidden:
                logger.error(f"Missing permissions to send message or create thread in channel {CHANNEL_ID}.")
            except discord.HTTPException as e:
                logger.error(f"Discord API error while posting: {e.status} - {e.text}")

        except Exception as e:
            logger.exception(f"An unexpected error occurred in post_and_exit: {e}")
            if target_channel:
                try:
                    await target_channel.send(f"🤖 An unexpected error occurred: {e}")
                except discord.Forbidden:
                    logger.error(f"Missing permissions to send error message in channel {CHANNEL_ID}.")
                except discord.HTTPException as http_e:
                     logger.error(f"Discord API error while sending error message: {http_e.status} - {http_e.text}")

        finally:
            logger.info("Task finished, initiating bot shutdown.")
            await self.close()

    async def get_daily_problem(self) -> Optional[LeetCodeProblem]:
        if not self._http_session:
            logger.error("aiohttp session not initialized.")
            return None

        query = """
            query questionOfToday {
                activeDailyCodingChallengeQuestion {
                    date
                    link
                    question {
                        difficulty
                        questionFrontendId
                        title
                    }
                }
            }
        """
        payload = {
            "operationName": "questionOfToday",
            "query": query,
            "variables": {}
        }

        try:
            async with self._http_session.post(LEETCODE_GRAPHQL_URL, json=payload) as response:
                response.raise_for_status()
                data = await response.json()

                if not isinstance(data, dict):
                    logger.error(f"API returned non-dict data: {type(data)}")
                    return None

                challenge_data = data.get("data", {}).get("activeDailyCodingChallengeQuestion")
                if not challenge_data:
                    logger.error("API response missing 'activeDailyCodingChallengeQuestion' data.")
                    logger.debug(f"Full API response data: {data}")
                    return None

                question_data = challenge_data.get("question")
                if not question_data:
                    logger.error("API response missing 'question' data within challenge.")
                    logger.debug(f"Challenge data: {challenge_data}")
                    return None

                problem_id = question_data.get("questionFrontendId", "N/A")
                title = question_data.get("title", "Unknown Title")
                link = challenge_data.get("link", "")
                difficulty = question_data.get("difficulty", "Unknown")
                date = challenge_data.get("date", "Unknown Date")

                return LeetCodeProblem(
                    id=problem_id,
                    title=title,
                    link=link,
                    difficulty=difficulty,
                    date=date
                )

        except aiohttp.ClientResponseError as e:
            logger.error(f"HTTP Error fetching problem: {e.status} {e.message}")
        except aiohttp.ClientConnectionError as e:
            logger.error(f"Connection Error fetching problem: {e}")
        except asyncio.TimeoutError:
            logger.error("Timeout while fetching LeetCode problem.")
        except Exception as e:
            logger.exception(f"Error processing LeetCode API response: {e}")

        return None

    def create_problem_embed(self, problem: LeetCodeProblem) -> discord.Embed:
        embed = discord.Embed(
            title=f"{problem.id}. {problem.title}",
            url=f"{LEETCODE_BASE_URL}{problem.link}",
            color=DIFFICULTY_COLORS.get(problem.difficulty, DIFFICULTY_COLORS["Unknown"]),
            description=f"Today's daily challenge ({problem.date})"
        )
        embed.add_field(
            name="Difficulty",
            value=f"{DIFFICULTY_EMOJIS.get(problem.difficulty, DIFFICULTY_EMOJIS['Unknown'])} {problem.difficulty}",
            inline=True
        )
        embed.set_footer(text="Click the title to open the problem on LeetCode.")
        return embed

    def format_thread_title(self, problem: LeetCodeProblem) -> str:
        emoji = DIFFICULTY_EMOJIS.get(problem.difficulty, DIFFICULTY_EMOJIS["Unknown"])
        max_len = 95 - len(emoji) - len(problem.id)
        truncated_title = problem.title[:max_len] + "..." if len(problem.title) > max_len else problem.title
        return f"{emoji} [Daily] {problem.id}. {truncated_title}"

if __name__ == "__main__":
    try:
        client = LeetCodeCronBot()
        client.run(TOKEN, log_handler=None)
    except discord.LoginFailure:
        logger.error("Failed to log in: Invalid Discord Token provided.")
    except Exception as e:
        logger.exception(f"Critical error during bot startup or runtime: {e}")
