import os
import asyncio
from dotenv import load_dotenv
from supabase import create_async_client

load_dotenv()
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

async def main():
    print("Creating async client...")
    supabase = await create_async_client(SUPABASE_URL, SUPABASE_KEY)
    
    def on_insert(payload):
        print("PAYLOAD RECEIVED:", payload)

    print("Subscribing...")
    channel = supabase.channel("comandos_bot")
    channel.on_postgres_changes(
        event="INSERT", 
        schema="public", 
        table="comandos_bot", 
        callback=on_insert
    )
    try:
        await channel.subscribe()
        print("Subscribed successfully. Waiting 5 seconds...")
        await asyncio.sleep(5)
    except Exception as e:
        print("Error:", e)
    finally:
        await supabase.dispose()

if __name__ == "__main__":
    asyncio.run(main())
