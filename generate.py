import asyncio
import os

# checks if pyrogram is installed or not
try:
	import pyrogram
except:
	print("\nPyrogram Not Found! Installing it via pip...")
	os.system("pip install pyrogram")
	print("\nPyrogram Installed Successfully!")

# imports pyrogram client
from pyrogram import Client as c

# clears screen for better looks
os.system("clear")

print("\nPyrogram Session String Generator\n")
print(f"\nYou can get ID and Hash on the official telegram website.\n")

# input fields for api id and hash
API_ID = input("\nEnter Your API_ID:\n > ")
API_HASH = input("\nEnter Your API_HASH:\n > ")

print("\n\n Enter Telegram Phone number when asked.\n\n")

i = c(":memory:", api_id=API_ID, api_hash=API_HASH)

async def main():
	await i.start()
	ss = await i.export_session_string()
	print("\nHERE IS YOUR SESSION STRING/ID, COPY IT, DON'T SHARE!!\n")
	print(f"\n{ss}\n")


asyncio.run(main())