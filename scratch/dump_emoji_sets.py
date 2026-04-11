import asyncio
import json
import database

async def main():
    await database.init_db()
    pool = await database.get_pool()
    rows = await pool.fetch('SELECT set_id, name, data FROM global_emoji_sets')
    
    output = []
    for row in rows:
        data = row['data']
        if isinstance(data, str):
            data = json.loads(data)
        output.append({
            "set_id": row['set_id'],
            "name": row['name'],
            "data": data
        })
    
    print(json.dumps(output, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    asyncio.run(main())
