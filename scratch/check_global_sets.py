import asyncio
import database
import json

async def check():
    await database.init_db()
    sets = await database.get_all_global_emoji_sets()
    print(f"SETS_COUNT: {len(sets)}")
    for s in sets:
        print(f"SET: {s['set_id']} - {s['name']}")

if __name__ == "__main__":
    asyncio.run(check())
