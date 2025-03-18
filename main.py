import discord
import requests
import asyncio
import os
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
CHANNEL_ID = int(os.getenv("DISCORD_CHANNEL_ID"))

DIFFICULTY_COLORS = {
    "Easy": 0x00FF00,  # Green
    "Medium": 0xFFFF00,  # Yellow
    "Hard": 0xFF0000    # Red
}

DIFFICULTY_EMOJIS = {
    "Easy": "🟢",
    "Medium": "🟡",
    "Hard": "🔴"
}

class LeetCodeCronBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        super().__init__(intents=intents)
        self.session = requests.Session()
        
    async def setup_hook(self):
        self.bg_task = self.loop.create_task(self.post_and_exit())
    
    async def post_and_exit(self):
        await self.wait_until_ready()
        
        try:
            problem_data = self.get_daily_problem()
            if not problem_data:
                print("Failed to get daily problem. Exiting.")
                await self.close()
                return
                
            title, link, difficulty, date, prob_id = problem_data

            channel = self.get_channel(CHANNEL_ID)
            if not channel:
                print(f"Channel {CHANNEL_ID} not found. Exiting.")
                await self.close()
                return

            embed = discord.Embed(
                title=f"{prob_id}. {title}",
                url=f"https://leetcode.com{link}",
                color=DIFFICULTY_COLORS.get(difficulty, 0x808080)
            )
            embed.add_field(name="Difficulty", value=difficulty, inline=True)

            thread_title = self.format_thread_title(title, difficulty, prob_id)

            print(f"Posting problem: {thread_title}")
            message = await channel.send(embed=embed)

            await message.create_thread(name=thread_title)
            print("Daily challenge posted successfully")
            
        except Exception as e:
            print(f"Error: {str(e)}")
        finally:

            await self.close()
    
    def get_daily_problem(self):
        try:
            self.session.get("https://leetcode.com/graphql")
            csrf_token = self.session.cookies.get("csrftoken")

            self.session.headers.update({
                "Referer": "https://leetcode.com",
                "X-CSRFToken": csrf_token,
                "Content-Type": "application/json"
            })
            
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
            
            response = self.session.post(
                "https://leetcode.com/graphql",
                json={
                    "operationName": "questionOfToday",
                    "query": query,
                    "variables": {}
                }
            )
            
            if response.status_code != 200:
                print(f"API error: {response.status_code}")
                return None
            
            data = response.json()
            challenge = data.get("data", {}).get("activeDailyCodingChallengeQuestion", {})
            question = challenge.get("question", {})
            
            return (
                question.get("title"),
                challenge.get("link"),
                question.get("difficulty"),
                challenge.get("date"),
                question.get("questionFrontendId")
            )
            
        except Exception as e:
            print(f"Error getting problem: {str(e)}")
            return None
    
    def format_thread_title(self, title, difficulty, prob_id):
        emoji = DIFFICULTY_EMOJIS.get(difficulty, "⚪")
        return f"{emoji} [Daily] {prob_id}. {title}"

if __name__ == "__main__":
    client = LeetCodeCronBot()
    client.run(TOKEN)
