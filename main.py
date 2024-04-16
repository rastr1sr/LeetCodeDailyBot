from datetime import datetime
from dotenv import load_dotenv
from os import environ

import discord
import requests

load_dotenv()

token = environ["DISCORD_TOKEN"]
channel_id = int(environ["DISCORD_CHANNEL_ID"])
default_ping = environ["DISCORD_DEFAULT_PING"]


intents = discord.Intents.default()
client = discord.Client(intents=intents)


def create_message_body(problem_title, current_date, url):
    lc_url = f"https://leetcode.com{url}"
    message_body = f"LeetCode daily - {problem_title} - {current_date} - <{lc_url}>"
    print(f"Message body: '{message_body}'")
    return message_body


def create_thread_title(problem_title, current_date):
    thread_title = f"LeetCode daily - {problem_title} - {current_date}"
    print(f"Thread title: '{thread_title}'")
    return thread_title


def create_thread_message_body(ping):
    message_body = f"<@&{ping}>"
    print(f"Thread message body: '{message_body}'")
    return message_body


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
                        title
                      }
                    }
                    }
                    """
    data["variables"] = None
    session.headers["Referer"] = "https://leetcode.com"
    session.headers['X-CSRFToken'] = session.cookies.get("csrftoken")
    response = session.post(lc_url, data=data)
    json = response.json()

    lc_link = json["data"]["activeDailyCodingChallengeQuestion"]["link"]
    lc_difficulty = json["data"]["activeDailyCodingChallengeQuestion"]["question"]["difficulty"]
    lc_title = json["data"]["activeDailyCodingChallengeQuestion"]["question"]["title"]
    lc_date = json["data"]["activeDailyCodingChallengeQuestion"]["date"]
    return lc_title, lc_link, lc_difficulty, lc_date


session = requests.Session()
get_csrf_token(session)
title, link, difficulty, date = get_daily(session)


async def send_message():
    message_body = create_message_body(title, date, link)
    thread_title = create_thread_title(title, date)
    thread_body = create_thread_message_body(default_ping)
    channel = client.get_channel(channel_id)
    message = await channel.send(message_body)
    thread = await message.create_thread(name=thread_title)
    await thread.send(thread_body)
    await client.close()


@client.event
async def on_ready():
    await send_message()


client.run(token)
