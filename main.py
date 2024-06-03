from datetime import datetime
from dotenv import load_dotenv
from os import environ

import discord
import requests

load_dotenv()

token = environ["DISCORD_TOKEN"]
channel_id = int(environ["DISCORD_CHANNEL_ID"])
default_ping = environ["DISCORD_DEFAULT_PING"]
easy_ping = environ["DISCORD_EASY_PING"]
medium_ping = environ["DISCORD_MEDIUM_PING"]
hard_ping = environ["DISCORD_HARD_PING"]

difficulty_pings = {"Easy": easy_ping, "Medium": medium_ping, "Hard": hard_ping}


intents = discord.Intents.default()
client = discord.Client(intents=intents)


def create_message_body(url, ping, diff):
    lc_url = f"https://leetcode.com{url}"
    message_body = f"<{lc_url}>" + "\n" + f"<@&{ping}>, <@&{difficulty_pings.get(diff)}>"
    print(f"Message body: '{message_body}'")
    return message_body


def create_thread_title(problem_title, current_date, prob_difficulty, prob_id):
    map = {"Easy": "🟢", "Medium": "🟡", "Hard": "🔴"}
    difficulty_color = map[prob_difficulty]
    thread_title = f"{difficulty_color} [Daily] {prob_id}. {problem_title}"
    print(f"Thread title: '{thread_title}'")
    return thread_title


def get_csrf_token(session):
    response = session.get("https://leetcode.com/graphql")
    print(response.cookies.get_dict())


def get_daily(session):
    lc_url = "https://leetcode.com/graphql"
    data = {}
    data["operationName"] = "questionOfToday"
    data["query"] = """
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
    data["variables"] = None
    session.headers["Referer"] = "https://leetcode.com"
    session.headers["X-CSRFToken"] = session.cookies.get("csrftoken")
    response = session.post(lc_url, data=data)
    lc_data = response.json()["data"]["activeDailyCodingChallengeQuestion"]

    lc_date, lc_link, lc_question = lc_data["date"], lc_data["link"], lc_data["question"]
    lc_difficulty, lc_id, lc_title = lc_question["difficulty"], lc_question["questionFrontendId"], lc_question["title"]
    return lc_title, lc_link, lc_difficulty, lc_date, lc_id


session = requests.Session()
get_csrf_token(session)
title, link, difficulty, date, id = get_daily(session)


async def send_message():
    message_body = create_message_body(link, default_ping, difficulty)
    thread_title = create_thread_title(title, date, difficulty, id)
    channel = client.get_channel(channel_id)
    message = await channel.send(message_body)
    await message.create_thread(name=thread_title)
    await client.close()


@client.event
async def on_ready():
    await send_message()


client.run(token)
