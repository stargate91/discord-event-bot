import asyncio
import database
async def main():
    try:
        await database.init_db()
        print(await database.get_global_setting("bot_presence_list"))
    except Exception as e:
        print(f"Error: {e}")
asyncio.run(main())
