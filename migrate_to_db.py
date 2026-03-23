"""
One-time migration: import user_gear.json and gs_data.json into the boopfish PostgreSQL database.

Usage:
    python migrate_to_db.py [gear_file] [gs_file]

Defaults:
    gear_file = user_gear.json
    gs_file   = gs_data.json

The script reads DATABASE_URL from .env (or the environment) and upserts each
Discord user's data into the users table, keyed by discord_id.

Safe to run multiple times — it only upserts, never deletes.
"""

import asyncio, asyncpg, json, os, sys
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")


async def migrate(gear_file: str, gs_file: str):
    if not DATABASE_URL:
        print("ERROR: DATABASE_URL is not set. Check your .env file.")
        sys.exit(1)

    # Load JSON files
    gear_data: dict[str, str] = {}
    if os.path.exists(gear_file):
        with open(gear_file) as f:
            gear_data = json.load(f)
        print(f"Loaded {len(gear_data)} entries from {gear_file}")
    else:
        print(f"Warning: {gear_file} not found — skipping gear images.")

    gs_data: dict[str, dict] = {}
    if os.path.exists(gs_file):
        with open(gs_file) as f:
            gs_data = json.load(f)
        print(f"Loaded {len(gs_data)} entries from {gs_file}")
    else:
        print(f"Warning: {gs_file} not found — skipping gear scores.")

    all_ids = set(gear_data.keys()) | set(gs_data.keys())
    if not all_ids:
        print("Nothing to migrate.")
        return

    pool = await asyncpg.create_pool(DATABASE_URL)

    success = 0
    skipped = 0
    for discord_id in all_ids:
        fields: dict = {}
        if discord_id in gear_data:
            fields['gear_image_url'] = gear_data[discord_id]
        if discord_id in gs_data:
            stats = gs_data[discord_id]
            if 'ap'  in stats: fields['gear_ap']  = stats['ap']
            if 'aap' in stats: fields['gear_aap'] = stats['aap']
            if 'dp'  in stats: fields['gear_dp']  = stats['dp']

        if not fields:
            skipped += 1
            continue

        col_list     = ', '.join(fields.keys())
        placeholders = ', '.join(f'${i + 2}' for i in range(len(fields)))
        set_clause   = ', '.join(f'{k} = EXCLUDED.{k}' for k in fields)
        params       = [discord_id] + list(fields.values())

        sql = f"""
            INSERT INTO users (discord_id, username, password_hash, role, {col_list})
            VALUES ($1, 'discord_' || $1, '', 'member', {placeholders})
            ON CONFLICT (discord_id) DO UPDATE SET
                {set_clause},
                updated_at = NOW()
        """
        try:
            await pool.execute(sql, *params)
            print(f"  OK  discord_id={discord_id}  fields={list(fields.keys())}")
            success += 1
        except Exception as e:
            print(f"  ERR discord_id={discord_id}: {e}")
            skipped += 1

    await pool.close()
    print(f"\nDone. {success} migrated, {skipped} skipped/errored out of {len(all_ids)} total.")


if __name__ == '__main__':
    gear_file = sys.argv[1] if len(sys.argv) > 1 else 'user_gear.json'
    gs_file   = sys.argv[2] if len(sys.argv) > 2 else 'gs_data.json'
    asyncio.run(migrate(gear_file, gs_file))
