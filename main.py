import discord
import aiohttp
import asyncio
import os
import logging
import sys
from dotenv import load_dotenv
from dataclasses import dataclass
from typing import Optional

load_dotenv()

@dataclass
class BotConfig:
    discord_token: str
    channel_id: int
    leetcode_graphql_url: str = "https://leetcode.com/graphql"
    leetcode_base_url: str = "https://leetcode.com"
    thread_archive_duration: int = 10080

    @classmethod
    def from_env(cls):
        token = os.getenv("DISCORD_TOKEN")
        if not token:
            raise ValueError("DISCORD_TOKEN not found in environment variables.")

        try:
            channel_id = int(os.getenv("DISCORD_CHANNEL_ID", "0"))
            if channel_id == 0:
                raise ValueError("DISCORD_CHANNEL_ID must be a non-zero integer.")
        except (ValueError, TypeError):
            raise ValueError("Invalid DISCORD_CHANNEL_ID. Please set a valid integer ID.")

        return cls(discord_token=token, channel_id=channel_id)

@dataclass
class LeetCodeProblem:
    id: str
    title: str
    link: str
    difficulty: str
    date: str

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

class LeetCodeAPIClient:
    _GET_DAILY_CHALLENGE_QUERY = """
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

    def __init__(self, session: aiohttp.ClientSession, url: str):
        self._session = session
        self._url = url

    async def get_daily_problem(self) -> Optional[LeetCodeProblem]:
        payload = {"query": self._GET_DAILY_CHALLENGE_QUERY}
        try:
            async with self._session.post(self._url, json=payload) as response:
                response.raise_for_status()
                data = await response.json()
                
                challenge_data = data["data"]["activeDailyCodingChallengeQuestion"]
                question_data = challenge_data["question"]

                return LeetCodeProblem(
                    id=question_data["questionFrontendId"],
                    title=question_data["title"],
                    link=challenge_data["link"],
                    difficulty=question_data["difficulty"],
                    date=challenge_data["date"]
                )
        except aiohttp.ClientResponseError as e:
            logger.error(f"HTTP Error fetching problem: {e.status} {e.message}")
        except (KeyError, TypeError) as e:
            logger.error(f"Failed to parse LeetCode API response. Structure may have changed. Error: {e}")
        except Exception as e:
            logger.exception(f"An unexpected error occurred while fetching the LeetCode problem: {e}")
        
        return None

class LeetCodeCronBot(discord.Client):
    def __init__(self, config: BotConfig):
        super().__init__(intents=discord.Intents.default())
        self.config = config
        self.api_client: Optional[LeetCodeAPIClient] = None
        self._http_session: Optional[aiohttp.ClientSession] = None
        self.bg_task: Optional[asyncio.Task] = None

    async def setup_hook(self):
        logger.info("Setting up bot resources...")
        self._http_session = aiohttp.ClientSession(headers={"User-Agent": "DiscordBot/LeetCodeDaily/2.0"})
        self.api_client = LeetCodeAPIClient(self._http_session, self.config.leetcode_graphql_url)
        self.bg_task = self.loop.create_task(self.post_daily_challenge_and_exit())

    async def on_ready(self):
        logger.info(f'Logged in as {self.user.name} ({self.user.id})')

    async def close(self):
        logger.info("Closing bot and cleaning up resources...")
        if self.bg_task and not self.bg_task.done():
            self.bg_task.cancel()
        if self._http_session and not self._http_session.closed:
            await self._http_session.close()
            logger.info("aiohttp session closed.")
        await super().close()
        logger.info("Discord client closed.")

    def _create_problem_embed(self, problem: LeetCodeProblem) -> discord.Embed:
        color = DIFFICULTY_COLORS.get(problem.difficulty, DIFFICULTY_COLORS["Unknown"])
        emoji = DIFFICULTY_EMOJIS.get(problem.difficulty, DIFFICULTY_EMOJIS["Unknown"])

        embed = discord.Embed(
            title=f"{problem.id}. {problem.title}",
            url=f"{self.config.leetcode_base_url}{problem.link}",
            color=color,
            description=f"Here is the daily challenge for {problem.date}."
        )
        embed.add_field(
            name="Difficulty",
            value=f"{emoji} {problem.difficulty}",
            inline=True
        )
        embed.set_footer(text="Click the title to open the problem on LeetCode.")
        return embed

    def _format_thread_title(self, problem: LeetCodeProblem) -> str:
        emoji = DIFFICULTY_EMOJIS.get(problem.difficulty, DIFFICULTY_EMOJIS["Unknown"])
        base_text = f"{emoji} [Daily] {problem.id}. "
        max_title_len = 100 - len(base_text)
        truncated_title = (
            problem.title[:max_title_len-3] + "..."
            if len(problem.title) > max_title_len
            else problem.title
        )
        return f"{base_text}{truncated_title}"

    async def post_daily_challenge_and_exit(self):
        await self.wait_until_ready()
        
        target_channel = self.get_channel(self.config.channel_id)
        if not isinstance(target_channel, discord.TextChannel):
            logger.error(f"Channel ID {self.config.channel_id} is not a valid text channel.")
            await self.close()
            return

        try:
            logger.info("Fetching daily LeetCode problem...")
            if not self.api_client:
                 logger.error("API client not initialized.")
                 return

            problem = await self.api_client.get_daily_problem()
            if not problem:
                logger.error("Failed to fetch daily problem details.")
                await target_channel.send("❌ Failed to fetch the LeetCode daily challenge today.")
                return

            logger.info(f"Successfully fetched: {problem.id}. {problem.title}")
            
            embed = self._create_problem_embed(problem)
            thread_title = self._format_thread_title(problem)

            logger.info(f"Posting to channel #{target_channel.name}")
            message = await target_channel.send(embed=embed)
            await message.create_thread(name=thread_title, auto_archive_duration=self.config.thread_archive_duration)
            logger.info(f"Successfully posted and created thread: '{thread_title}'")
            
            logger.info("Work complete. Forcing immediate exit to prevent hanging.")
            sys.exit(0)

        except discord.Forbidden:
            logger.error(f"Missing permissions to send message or create thread in channel {self.config.channel_id}.")
        except discord.HTTPException as e:
            logger.error(f"Discord API error: {e.status} - {e.text}")
        except Exception as e:
            logger.exception(f"An unexpected error occurred in the main task: {e}")
            if target_channel:
                try:
                    await target_channel.send(f"🤖 An unexpected error occurred: {type(e).__name__}")
                except discord.HTTPException:
                    pass
        finally:
            logger.info("Task finished, initiating bot shutdown.")
            await self.close()

if __name__ == "__main__":
    try:
        bot_config = BotConfig.from_env()
        client = LeetCodeCronBot(config=bot_config)
        client.run(bot_config.discord_token, log_handler=None)
    except ValueError as e:
        logger.error(f"Configuration Error: {e}")
    except discord.LoginFailure:
        logger.error("Failed to log in: Invalid Discord Token provided.")
    except Exception as e:
        logger.exception(f"Critical error during bot startup or runtime: {e}")
