import discord
import requests
import time
import asyncio
import schedule
from datetime import datetime, timedelta
import itertools
import os
from discord import Intents
import json
import math
from keep_alive import keep_alive

# Configuration (replace with your information)
api_keys = ["Srs5FpFlYiedB3hp"]  # Add your API keys here
bot_token = "YOUR_BOT_TOKEN"  # Replace with your Discord bot token
tracked_users = [3239922]  # Add user IDs you want to track
sales_threshold = 50_000_000  # Threshold for sending alerts (50 million)
bot_token = os.environ['TOKEN']
CHANNEL_ID = os.environ['CHANNEL_ID']
print(CHANNEL_ID)

# Data structure to store user information
user_data = {}


def calculate_check_interval(user_data, api_keys):
  num_users = len(user_data)
  print(len(user_data))
  num_keys = len(api_keys)
  max_api_calls_per_key = 25  # Maximum API calls per minute per key
  total_api_calls_needed = num_users  # Assuming 1 API call per user per check
  total_max_api_calls = num_keys * max_api_calls_per_key
  interval = math.ceil(total_api_calls_needed / total_max_api_calls)
  if interval < 1:
    interval = 1
  print(interval)
  return interval


def load_api_keys():
  global api_keys
  global api_key_cycle
  try:
    with open("api_keys.txt", "r") as f:
      api_keys = list(f.read().splitlines())
      api_key_cycle = itertools.cycle(api_keys)
  except FileNotFoundError:
    pass  # If file not found, keep the default API keys


# Save API keys to file
def save_api_keys():
  with open("api_keys.txt", "w") as f:
    f.write("\n".join(api_keys))


load_api_keys()
print(api_keys)


# Function to add a new API key
def add_api_key(key):
  if key not in api_keys:
    api_keys.append(key)
    save_api_keys()
  else:
    print("API Key Already Exists")


def delete_api_key(key):
  if key in api_keys:
    api_keys.remove(key)
    save_api_keys()


def save_user_data():

  # Convert datetime objects to string representations
  for user_id, user_info in user_data.items():
    if user_info["last_check"] is not None and isinstance(
        user_info["last_check"], datetime):
      user_info["last_check"] = user_info["last_check"].isoformat()

  with open("user_data.json", "w") as f:
    json.dump(user_data, f)
  print("User data saved.")


def load_user_data():
  global user_data
  try:
    with open("user_data.json", "r") as f:
      user_data = json.load(f)
      # Convert string representations back to datetime objects
      for user_id, user_info in user_data.items():
        if user_info["last_check"] is not None:
          user_info["last_check"] = datetime.fromisoformat(
              user_info["last_check"])
  except FileNotFoundError:
    user_data = {}  # Initialize with an empty dictionary if file not found


load_user_data()
check_interval = calculate_check_interval(user_data, api_keys)
check_interval = 5


def add_user(user_id):
  if user_id not in user_data:
    user_data[user_id] = {
        "last_check": None,
        "last_seen": None,
        "bazaar_value": 0,  # Store total bazaar value
        "total_sales": 0
    }
    print(f"Added user {user_id} to tracking list")
  else:
    print(f"User {user_id} is already being tracked")


def add_faction(faction_id):
  api_key = next(api_key_cycle)
  try:
    response = requests.get(
        f"https://api.torn.com/faction/{faction_id}?selections=&key={api_key}")
    response.raise_for_status()
    faction_data = response.json()
    members = faction_data["members"]
    for member_id in members:
      add_user(member_id)
  except requests.exceptions.RequestException as e:
    print(f"Error fetching faction data: {e}")


def delete_user(user_id):
  if user_id in user_data:
    del user_data[user_id]
    print(f"Deleted user {user_id} from tracking list")
  else:
    print(f"User {user_id} is not being tracked")


# Function to delete users from a faction
def delete_faction(faction_id):
  api_key = next(api_key_cycle)
  try:
    response = requests.get(
        f"https://api.torn.com/faction/{faction_id}?selections=&key={api_key}")
    response.raise_for_status()
    faction_data = response.json()
    members = faction_data["members"]
    for member_id in members:
      delete_user(member_id)
  except requests.exceptions.RequestException as e:
    print(f"Error fetching faction data: {e}")


# Initialize user data
for user_id in tracked_users:
  user_data[user_id] = {
      "last_check": None,
      "last_seen": None,
      "bazaar_value": 0,
      "total_sales": 0
  }


# API call function with key rotation
def make_api_call(user_id, api_key):
  try:
    response = requests.get(
        f"https://api.torn.com/user/{user_id}?selections=bazaar&profile&key={api_key}"
    )
    response.raise_for_status()  # Raise an error for bad status codes
    data = response.json()
    if "error" in data and data["error"]["code"] == 2:
      print("Invalid API key. Please use a valid API key.")
      delete_api_key(api_key)
      return None
    else:
      return data
  except requests.exceptions.RequestException as e:
    print(f"Error with API key: {e}")
    # You could consider adding logic here to blacklist a failing key temporarily
    # ...
    return make_api_call(user_id)  # Retry with the next key


def check_user(user_id, api_key):
  try:
    response = requests.get(
        f"https://api.torn.com/user/{user_id}?selections=profile&key={api_key}"
    )
    response.raise_for_status()  # Raise an error for bad status codes
    data = response.json()
    if "error" in data and data["error"]["code"] == 2:
      print("Invalid API key. Please use a valid API key.")
      delete_api_key(api_key)
      return None
    else:
      return data

  except requests.exceptions.RequestException as e:
    print(f"Error fetching status for user {user_id}: {e}")
    return False  # Return false on error


# Function to check a user's bazaar and update data
def check_user_bazaar(user_id):
  api_key = next(api_key_cycle)
  profile = check_user(user_id, api_key)
  if not profile:
    return None

  name = profile["name"]

  # Check if user is in hospital or traveling
  if profile["status"]["state"] in ["Hospital", "Traveling"]:
    print(f"{name} is in {profile['status']['state']}. Skipping.")
    return

  if profile["last_action"]["status"] == "Online":
    print(f"{name} is online. Skipping.")
    return

  # Extract last action timestamp and online status
  last_action = profile["last_action"]["relative"]

  data = make_api_call(user_id, api_key)
  if not data:
    return None

  bazaar = data["bazaar"]

  current_total_value = sum(item["price"] for item in bazaar)

  # Update user data
  user = user_data[user_id]
  user["last_check"] = datetime.utcnow()
  user["last_seen"] = last_action

  # Initialize bazaar_value on first check
  if user["bazaar_value"] == 0:
    user["bazaar_value"] = current_total_value
    return  # Skip sales calculation for this first check

  # Calculate sales based on total value difference (for subsequent checks)
  sales_value = user["bazaar_value"] - current_total_value

  user["bazaar_value"] = current_total_value

  # Check if alert condition is met
  if sales_value >= sales_threshold:
    send_discord_alert(user_id, sales_value, current_total_value, name)


# Function to format and send Discord alert
def send_discord_alert(user_id, sales_value, current_total_value, name):
  print("sending alert")
  user_name = name
  last_seen_time = user_data[user_id]["last_seen"]
  last_seen_str = f"Active {last_seen_time}" if last_seen_time else "Offline"

  profile_link = f"https://www.torn.com/profiles.php?XID={user_id}"

  embed = discord.Embed(
      title=f"{user_name} just sold items worth ${sales_value:,}",
      color=0x00ff00)
  embed.add_field(name="Currently",
                  value=f":green_circle: {last_seen_str}",
                  inline=True)
  embed.add_field(name="Bazaar Value",
                  value=f"${current_total_value:,}",
                  inline=True)
  embed.add_field(name="Profile Link",
                  value=f"[Torn Profile]({profile_link})",
                  inline=False)

  # Add additional fields as needed (e.g., specific items sold)
  # ...

  # Send the embed to your desired Discord channel
  channel = client.get_guild(835870958039990283).get_channel(
      1227194495356112957)
  print(channel)
  message_content = "@everyone"  # Add @everyone here
  asyncio.run_coroutine_threadsafe(
      channel.send(content=message_content, embed=embed), client.loop)


# Background task to periodically check users
async def check_users():
  print("checking users")
  while True:
    for user_id in set(user_data.keys()):
      check_user_bazaar(user_id)
      print(f"Checked user {user_id}")
      await asyncio.sleep(check_interval)


# Schedule the task using schedule library
# schedule.every(check_interval).seconds.do(check_users)

# Discord bot setup
intents = Intents.default()
intents.typing = False
intents.presences = False
intents.messages = True  # Adjust based on your bot's functionality
client = discord.Client(intents=intents)


@client.event
async def on_ready():
  print(f'Logged in as {client.user}')
  asyncio.create_task(check_users())
  schedule.every(0.5).minutes.do(save_user_data)
  while True:
    schedule.run_pending()
    await asyncio.sleep(1)


@client.event
async def on_message(message):
  global check_interval
  if message.content.startswith("!add") or message.content.startswith(
      "!delete"):  # Handle both add and delete commands
    args = message.content.split()
    if len(args) >= 3:
      command, type_, id_ = args[:3]
      try:
        if type_ == "user":
          id_ = int(id_)
          if command == "!add":
            add_user(id_)
            await message.channel.send(f"Added user {id_} to tracking list")
          elif command == "!delete":
            delete_user(id_)
            await message.channel.send(f"Deleted user {id_} from tracking list"
                                       )
        elif type_ == "faction":
          id_ = int(id_)
          if command == "!add":
            add_faction(id_)
            await message.channel.send(f"Added users from faction {id_}")
          elif command == "!delete":
            delete_faction(id_)
            await message.channel.send(f"Deleted users from faction {id_}")
        elif type_ == "key":
          if command == "!add":
            add_api_key(id_)
            await message.channel.send(f"Added API key {id_}")
          elif command == "!delete":
            delete_api_key(id_)
            await message.channel.send(f"Deleted API key {id_}")
        else:
          await message.channel.send(
              "Invalid command. Use !add/!delete user <user_id> or !add/!delete faction <faction_id>"
          )
        check_interval = calculate_check_interval(user_data, api_keys)
      except ValueError:
        await message.channel.send("Invalid ID. Please provide a numeric ID.")
    else:
      await message.channel.send(
          "Invalid command format. Use !add/!delete user <user_id> or !add/!delete faction <faction_id>"
      )


# Run the bot
keep_alive()
client.run(bot_token)
