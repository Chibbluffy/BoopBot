"""Shared database pool and helper functions used across all cogs."""

from __future__ import annotations
import asyncpg, os, random
import string as _string
from datetime import datetime, timezone

pool: asyncpg.Pool = None  # assigned in bot.main() before cogs load

# ── Env-derived constants ──────────────────────────────────────────────────────
NOTIFY_CHANNEL       = 'looking-for-group'
GUILD_MEMBER_ROLE_ID = int(os.getenv("GUILD_MEMBER_ROLE_ID", "0"))

# ── General helpers ────────────────────────────────────────────────────────────

def parse_discord_timestamp(ts):
    try:
        if ts.startswith('<t:') and ts.endswith('>'):
            parts = ts[3:-1].split(':')
            if parts:
                return datetime.fromtimestamp(int(parts[0]), tz=timezone.utc)
    except (ValueError, IndexError):
        pass
    return None

def split_reply(reply):
    for i in range(1999, 0, -1):
        if reply[i] == '\n':
            return reply[:i], reply[i:]
    for i in range(1999, 0, -1):
        if reply[i] == ' ':
            return reply[:i], reply[i:]
    return reply[:1999], reply[1999:]

def calculate_gs(ap, aap, dp):
    return (ap + aap) / 2 + dp

# ── Auth helpers ───────────────────────────────────────────────────────────────

async def is_admin(discord_id: str) -> bool:
    row = await pool.fetchrow("SELECT role FROM users WHERE discord_id = $1", discord_id)
    return row is not None and row['role'] == 'admin'

# ── Gear DB helpers ────────────────────────────────────────────────────────────

_ALLOWED_GEAR_COLS = {'gear_ap', 'gear_aap', 'gear_dp', 'gear_image_url'}

async def db_upsert_gear(discord_id, discord_username, **fields):
    fields = {k: v for k, v in fields.items() if k in _ALLOWED_GEAR_COLS}
    if not fields:
        return
    field_keys  = list(fields.keys())
    set_clause  = ', '.join(f'{k} = ${i+3}' for i, k in enumerate(field_keys))
    base_params = [discord_id, discord_username] + list(fields.values())

    result = await pool.execute(
        f"UPDATE users SET discord_username = $2, {set_clause}, updated_at = NOW() WHERE discord_id = $1",
        *base_params
    )
    if result != "UPDATE 0":
        return

    result = await pool.execute(
        f"UPDATE users SET discord_id = $1, discord_username = $2, {set_clause}, updated_at = NOW() "
        f"WHERE username = $2 AND discord_id IS NULL",
        *base_params
    )
    if result != "UPDATE 0":
        return

    col_list        = ', '.join(field_keys)
    placeholders    = ', '.join(f'${i+4}' for i in range(len(field_keys)))
    set_clause_excl = ', '.join(f'{k} = EXCLUDED.{k}' for k in field_keys)
    await pool.execute(
        f"""INSERT INTO users (discord_id, discord_username, username, password_hash, role, {col_list})
            VALUES ($1, $2, $3, '', 'member', {placeholders})
            ON CONFLICT (discord_id) DO UPDATE SET
                discord_username = EXCLUDED.discord_username,
                {set_clause_excl},
                updated_at = NOW()""",
        discord_id, discord_username, discord_username, *list(fields.values())
    )

async def db_get_user_gear(discord_id):
    return await pool.fetchrow(
        "SELECT gear_ap, gear_aap, gear_dp, gear_image_url FROM users WHERE discord_id = $1",
        discord_id
    )

async def db_get_all_with_gs():
    return await pool.fetch(
        """SELECT discord_id, discord_username,
                  COALESCE(gear_ap, 0)  AS gear_ap,
                  COALESCE(gear_aap, 0) AS gear_aap,
                  COALESCE(gear_dp, 0)  AS gear_dp
           FROM users
           WHERE (gear_ap IS NOT NULL OR gear_aap IS NOT NULL OR gear_dp IS NOT NULL)
             AND discord_id IS NOT NULL"""
    )

# ── Quote helpers ──────────────────────────────────────────────────────────────

_QUOTE_ID_CHARS = _string.ascii_lowercase + _string.digits

async def generate_quote_id() -> str:
    while True:
        nid = ''.join(random.choices(_QUOTE_ID_CHARS, k=5))
        if not await pool.fetchrow("SELECT 1 FROM quotes WHERE nadeko_id = $1", nid):
            return nid

# ── Economy DB helpers ─────────────────────────────────────────────────────────

async def ensure_economy_user(discord_id: str, username: str = ""):
    await pool.execute(
        """INSERT INTO users (discord_id, discord_username, username, password_hash, role)
           VALUES ($1, $2, $2, '', 'member')
           ON CONFLICT (discord_id) DO NOTHING""",
        discord_id, username or discord_id
    )

async def get_boops(discord_id: str) -> int:
    row = await pool.fetchrow("SELECT boops FROM users WHERE discord_id = $1", discord_id)
    return row["boops"] if row else 0

async def add_boops(discord_id: str, amount: int, username: str = "") -> int:
    await ensure_economy_user(discord_id, username)
    row = await pool.fetchrow(
        "UPDATE users SET boops = GREATEST(0, boops + $2) WHERE discord_id = $1 RETURNING boops",
        discord_id, amount
    )
    return row["boops"]

async def transfer_boops(from_id: str, to_id: str, amount: int) -> bool:
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                "SELECT boops FROM users WHERE discord_id = $1 FOR UPDATE", from_id
            )
            if not row or row["boops"] < amount:
                return False
            await conn.execute("UPDATE users SET boops = boops - $1 WHERE discord_id = $2", amount, from_id)
            await conn.execute("UPDATE users SET boops = boops + $1 WHERE discord_id = $2", amount, to_id)
            return True

# ── Fishing DB helpers ─────────────────────────────────────────────────────────

async def get_fishing_profile(discord_id: str) -> dict:
    row = await pool.fetchrow(
        "SELECT active_rod, active_float, active_bait FROM fishing_profile WHERE discord_id = $1",
        discord_id
    )
    if not row:
        await pool.execute(
            "INSERT INTO fishing_profile (discord_id) VALUES ($1) ON CONFLICT DO NOTHING", discord_id
        )
        return {"active_rod": "rod_starter", "active_float": None, "active_bait": None}
    return dict(row)

async def get_inventory(discord_id: str) -> dict:
    rows = await pool.fetch(
        "SELECT item_id, quantity FROM fishing_inventory WHERE discord_id = $1", discord_id
    )
    return {r["item_id"]: r["quantity"] for r in rows}

async def add_inventory(discord_id: str, item_id: str, qty: int):
    await pool.execute(
        """INSERT INTO fishing_inventory (discord_id, item_id, quantity) VALUES ($1, $2, $3)
           ON CONFLICT (discord_id, item_id) DO UPDATE
           SET quantity = fishing_inventory.quantity + $3""",
        discord_id, item_id, qty
    )

async def update_fish_record(discord_id: str, fish_name: str, size_kg: float) -> tuple[bool, float | None]:
    existing = await pool.fetchrow(
        "SELECT record_kg FROM fish_records WHERE discord_id = $1 AND fish_name = $2",
        discord_id, fish_name
    )
    is_new_record = existing is None or size_kg > existing["record_kg"]
    if existing is None:
        await pool.execute(
            """INSERT INTO fish_records (discord_id, fish_name, record_kg, catch_count, caught_at)
               VALUES ($1, $2, $3, 1, NOW())""",
            discord_id, fish_name, size_kg
        )
    elif is_new_record:
        await pool.execute(
            """UPDATE fish_records SET record_kg = $3, caught_at = NOW(), catch_count = catch_count + 1
               WHERE discord_id = $1 AND fish_name = $2""",
            discord_id, fish_name, size_kg
        )
    else:
        await pool.execute(
            "UPDATE fish_records SET catch_count = catch_count + 1 WHERE discord_id = $1 AND fish_name = $2",
            discord_id, fish_name
        )
    return is_new_record, existing["record_kg"] if existing else None

async def get_fish_records(discord_id: str):
    return await pool.fetch(
        """SELECT fish_name, record_kg, catch_count FROM fish_records
           WHERE discord_id = $1 ORDER BY record_kg DESC""",
        discord_id
    )

async def get_all_fish_leaderboards():
    """Top 5 per fish by record_kg, for all fish with any records."""
    return await pool.fetch(
        """SELECT fish_name, name, record_kg FROM (
               SELECT fr.fish_name,
                      COALESCE(NULLIF(u.discord_username,''), u.username) AS name,
                      fr.record_kg,
                      ROW_NUMBER() OVER (PARTITION BY fr.fish_name ORDER BY fr.record_kg DESC) AS rn
               FROM fish_records fr
               JOIN users u ON u.discord_id = fr.discord_id
           ) sub
           WHERE rn <= 5
           ORDER BY fish_name, rn"""
    )

async def use_bait(discord_id: str, bait_id: str) -> bool:
    result = await pool.execute(
        "UPDATE fishing_inventory SET quantity = quantity - 1 WHERE discord_id = $1 AND item_id = $2 AND quantity > 0",
        discord_id, bait_id
    )
    if result == "UPDATE 0":
        return False
    row = await pool.fetchrow(
        "SELECT quantity FROM fishing_inventory WHERE discord_id = $1 AND item_id = $2",
        discord_id, bait_id
    )
    if row and row["quantity"] <= 0:
        await pool.execute(
            "UPDATE fishing_profile SET active_bait = NULL WHERE discord_id = $1", discord_id
        )
    return True
