import discord
from discord.ext import commands, tasks
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import asyncpg, os
import utils

WEBSITE_URL = os.getenv("WEBSITE_URL", "https://boop.fish")

_ALL_CLASSES = sorted([
    "Warrior", "Sorceress", "Ranger", "Berserker", "Tamer",
    "Musa", "Maehwa", "Valkyrie", "Kunoichi", "Ninja",
    "Wizard", "Witch", "Dark Knight", "Striker", "Mystic",
    "Lahn", "Archer", "Shai", "Guardian", "Hashashin",
    "Nova", "Sage", "Corsair", "Drakania", "Woosa",
    "Maegu", "Scholar", "Dosa", "Deadeye",
])
BDO_CLASSES_1 = _ALL_CLASSES[:25]   # Archer – Valkyrie
BDO_CLASSES_2 = _ALL_CLASSES[25:]   # Warrior – Woosa

STATUS_COLORS = {
    "active": discord.Color.blurple(),
    "closed": discord.Color.dark_grey(),
}


async def fetch_class_emojis() -> dict:
    rows = await utils.pool.fetch("SELECT class_name, emoji_id, emoji_name, animated FROM class_emojis")
    result = {}
    for r in rows:
        if r["emoji_id"] and r["emoji_name"]:
            prefix = "a" if r["animated"] else ""
            result[r["class_name"]] = f"<{prefix}:{r['emoji_name']}:{r['emoji_id']}>"
        elif r["emoji_name"]:
            result[r["class_name"]] = r["emoji_name"]
    return result


async def fetch_event(event_id: str) -> dict | None:
    row = await utils.pool.fetchrow("SELECT * FROM events WHERE id = $1", event_id)
    return dict(row) if row else None


async def fetch_roles(event_id: str) -> list:
    rows = await utils.pool.fetch(
        "SELECT * FROM event_roles WHERE event_id = $1 ORDER BY display_order", event_id
    )
    return [dict(r) for r in rows]


async def fetch_signups(event_id: str) -> list:
    rows = await utils.pool.fetch(
        "SELECT * FROM event_signups WHERE event_id = $1 ORDER BY signup_order", event_id
    )
    return [dict(r) for r in rows]


async def build_event_embed(event: dict, roles: list, signups: list, class_emojis: dict) -> discord.Embed:
    color = STATUS_COLORS.get(event.get("status", "active"), discord.Color.blurple())
    embed = discord.Embed(
        title=event["title"],
        description=event.get("description") or "",
        color=color,
    )

    # ── Compute Unix timestamp once ───────────────────────────────────────────
    ts = None
    if event.get("event_date") and event.get("event_time"):
        try:
            tz_str   = event.get("event_timezone") or "UTC"
            date_s   = str(event["event_date"])[:10]
            time_s   = str(event["event_time"])[:5]
            dt_naive = datetime.strptime(f"{date_s} {time_s}", "%Y-%m-%d %H:%M")
            ts       = int(dt_naive.replace(tzinfo=ZoneInfo(tz_str)).timestamp())
        except Exception as e:
            print(f"[events] timestamp error: {e}")

    # ── Header: 2-column layout ───────────────────────────────────────────────
    accepted = [s for s in signups if s["status"] == "accepted"]
    bench    = [s for s in signups if s["status"] == "bench"]

    signup_str = str(len(accepted))
    if event.get("total_cap"):
        signup_str += f"/{event['total_cap']}"
    if bench:
        signup_str += f" (+{len(bench)})"

    date_val  = f"<t:{ts}:D>" if ts else "—"
    time_val  = f"<t:{ts}:t>" if ts else "—"
    countdown = f"<t:{ts}:R>" if ts else "—"

    embed.add_field(name="📋 Sign Ups",  value=f"{signup_str}\n⏰ {time_val}\n📅 {date_val}", inline=True)
    embed.add_field(name="⏱️ Countdown", value=countdown,                                      inline=True)
    embed.add_field(name="\u200b",       value="\u200b",                                        inline=True)  # fill row so roles start fresh

    # Spacing separator before roles (only if there are roles to show)
    if roles:
        embed.add_field(name="\u200b", value="─────────────────────", inline=False)

    # ── Role sections (2-column) ──────────────────────────────────────────────
    by_role: dict[str, list] = {}
    for s in signups:
        rid = str(s.get("role_id") or "")
        by_role.setdefault(rid, []).append(s)

    role_ids = {str(r["id"]) for r in roles}

    for i, role in enumerate(roles):
        rid   = str(role["id"])
        slots = [s for s in by_role.get(rid, []) if s["status"] == "accepted"]
        cap   = role.get("soft_cap")
        emoji = class_emojis.get(role["name"], "") or role.get("emoji") or ""

        header = f"{emoji} {role['name']}" if emoji else role["name"]
        header += f" ({len(slots)}/{cap})" if cap else f" ({len(slots)})"

        lines = []
        for s in slots:
            cls_emoji = class_emojis.get(s.get("bdo_class") or "", "")
            lines.append(
                f"{cls_emoji} {s['signup_order']} {s['discord_name']}"
                if cls_emoji else f"{s['signup_order']} {s['discord_name']}"
            )

        embed.add_field(name=header, value="\n".join(lines) or "*empty*", inline=True)
        # Insert blank spacer after every 2nd role to force a new row
        if i % 2 == 1:
            embed.add_field(name="\u200b", value="\u200b", inline=True)

    # No-role accepted signups
    no_role = [s for s in accepted if str(s.get("role_id") or "") not in role_ids]
    if no_role:
        lines = []
        for s in no_role:
            cls_emoji = class_emojis.get(s.get("bdo_class") or "", "")
            lines.append(
                f"{cls_emoji} {s['signup_order']} {s['discord_name']}"
                if cls_emoji else f"{s['signup_order']} {s['discord_name']}"
            )
        embed.add_field(name=f"📌 No Role ({len(no_role)})", value="\n".join(lines), inline=True)

    # ── Bench / Tentative / Absent ────────────────────────────────────────────
    bench_members     = [s for s in signups if s["status"] == "bench"]
    tentative_members = [s for s in signups if s["status"] == "tentative"]
    declined_members  = [s for s in signups if s["status"] == "declined"]
    absent_members    = [s for s in signups if s["status"] == "absent"]

    if bench_members or tentative_members or declined_members or absent_members:
        embed.add_field(name="\u200b", value="─────────────────────", inline=False)

    # Bench — grouped by the role they wanted
    if bench_members:
        by_wanted: dict[str, list] = {}
        for s in bench_members:
            key = s.get("role_name") or "No Role"
            by_wanted.setdefault(key, []).append(s)

        for role_name, members in by_wanted.items():
            parts = []
            for s in members:
                cls_emoji = class_emojis.get(s.get("bdo_class") or "", "")
                parts.append(
                    f"{cls_emoji} {s['signup_order']} {s['discord_name']}"
                    if cls_emoji else f"{s['signup_order']} {s['discord_name']}"
                )
            embed.add_field(
                name=f"🪑 Bench — {role_name} ({len(members)})",
                value=" · ".join(parts),
                inline=False,
            )

    # Tentative / Declined / Absent — flat list
    for label, icon, members in [("Tentative", "❓", tentative_members), ("Declined", "❌", declined_members), ("Absent", "🚫", absent_members)]:
        if members:
            parts = []
            for s in members:
                cls_emoji = class_emojis.get(s.get("bdo_class") or "", "")
                parts.append(
                    f"{cls_emoji} {s['signup_order']} {s['discord_name']}"
                    if cls_emoji else f"{s['signup_order']} {s['discord_name']}"
                )
            embed.add_field(
                name=f"{icon} {label} ({len(members)})",
                value=" · ".join(parts),
                inline=False,
            )

    embed.set_footer(text=f"Event ID: {event['id']}")
    return embed


async def _refresh_embed(message: discord.Message | None, event_id: str):
    if message is None:
        return
    try:
        event = await fetch_event(event_id)
        if not event:
            return
        roles   = await fetch_roles(event_id)
        signups = await fetch_signups(event_id)
        emojis  = await fetch_class_emojis()
        embed   = await build_event_embed(event, roles, signups, emojis)
        view    = EventSignupView(event_id, roles, status=event.get("status", "active"))
        await message.edit(embed=embed, view=view)
    except Exception as e:
        print(f"[events] embed refresh failed: {e}")


async def _sync_calendar_interest(event_id: str, discord_id: str, add: bool):
    """Add or remove a user's interest in the calendar event linked to this guild event."""
    ev = await utils.pool.fetchrow("SELECT calendar_event_id FROM events WHERE id = $1", event_id)
    if not ev or not ev["calendar_event_id"]:
        return
    user = await utils.pool.fetchrow("SELECT id FROM users WHERE discord_id = $1", discord_id)
    if not user:
        return
    cal_id = ev["calendar_event_id"]
    uid    = user["id"]
    if add:
        await utils.pool.execute(
            "INSERT INTO calendar_event_interests (event_id, user_id) VALUES ($1, $2) ON CONFLICT DO NOTHING",
            cal_id, uid,
        )
    else:
        await utils.pool.execute(
            "DELETE FROM calendar_event_interests WHERE event_id = $1 AND user_id = $2",
            cal_id, uid,
        )


async def _try_promote_bench(event_id: str, role_id, conn) -> None:
    """Promote the earliest bench signup for a role to accepted if caps allow."""
    event_row = await conn.fetchrow("SELECT total_cap FROM events WHERE id = $1", event_id)
    if event_row and event_row["total_cap"]:
        total_accepted = await conn.fetchval(
            "SELECT COUNT(*) FROM event_signups WHERE event_id = $1 AND status = 'accepted'",
            event_id,
        )
        if total_accepted >= event_row["total_cap"]:
            return

    if role_id:
        role_row = await conn.fetchrow("SELECT soft_cap FROM event_roles WHERE id = $1", role_id)
        if role_row and role_row["soft_cap"] is not None:
            role_accepted = await conn.fetchval(
                "SELECT COUNT(*) FROM event_signups WHERE event_id = $1 AND role_id = $2 AND status = 'accepted'",
                event_id, role_id,
            )
            if role_accepted >= role_row["soft_cap"]:
                return

    bench = await conn.fetchrow(
        """SELECT id FROM event_signups
           WHERE event_id = $1 AND role_id IS NOT DISTINCT FROM $2 AND status = 'bench'
           ORDER BY signup_order ASC LIMIT 1""",
        event_id, role_id,
    )
    if bench:
        await conn.execute(
            "UPDATE event_signups SET status = 'accepted' WHERE id = $1", bench["id"]
        )
        promoted = await conn.fetchrow(
            "SELECT discord_id, role_name FROM event_signups WHERE id = $1", bench["id"]
        )
        return dict(promoted) if promoted else None
    return None


async def _upsert_signup(event_id: str, discord_id: str, discord_name: str,
                         role_id, role_name, bdo_class, status: str):
    promoted_signup = None
    async with utils.pool.acquire() as conn:
        async with conn.transaction():
            # Lock the event row to serialize concurrent signups
            event_row = await conn.fetchrow(
                "SELECT id, total_cap FROM events WHERE id = $1 FOR UPDATE", event_id
            )

            # Cap enforcement: only applies when trying to be accepted
            if status == "accepted":
                # Count accepted signups on this event, excluding the current user
                # (they may be switching roles, so their old slot doesn't count against them)
                total_accepted = await conn.fetchval(
                    "SELECT COUNT(*) FROM event_signups WHERE event_id = $1 AND status = 'accepted' AND discord_id != $2",
                    event_id, discord_id,
                )
                if event_row["total_cap"] and total_accepted >= event_row["total_cap"]:
                    status = "bench"

            if status == "accepted" and role_id:
                role_row = await conn.fetchrow(
                    "SELECT soft_cap FROM event_roles WHERE id = $1", role_id
                )
                if role_row and role_row["soft_cap"] is not None:
                    role_accepted = await conn.fetchval(
                        "SELECT COUNT(*) FROM event_signups WHERE event_id = $1 AND role_id = $2 AND status = 'accepted' AND discord_id != $3",
                        event_id, role_id, discord_id,
                    )
                    if role_accepted >= role_row["soft_cap"]:
                        status = "bench"

            existing = await conn.fetchrow(
                "SELECT id, role_id, signup_order, status AS old_status FROM event_signups WHERE event_id = $1 AND discord_id = $2",
                event_id, discord_id,
            )
            if existing:
                existing_role = str(existing["role_id"]) if existing["role_id"] else None
                new_role      = str(role_id) if role_id else None
                role_changed  = existing_role != new_role
                if role_changed:
                    order_row = await conn.fetchrow(
                        "SELECT COALESCE(MAX(signup_order), 0) + 1 AS next_order FROM event_signups WHERE event_id = $1",
                        event_id,
                    )
                    new_order = order_row["next_order"]
                else:
                    new_order = existing["signup_order"]
                await conn.execute(
                    """UPDATE event_signups
                       SET role_id = $3, role_name = $4, bdo_class = $5, status = $6, discord_name = $7, signup_order = $8
                       WHERE event_id = $1 AND discord_id = $2""",
                    event_id, discord_id, role_id, role_name, bdo_class, status, discord_name, new_order,
                )
                # Freed an accepted slot in the old role — try to promote from bench
                if role_changed and existing["old_status"] == "accepted":
                    promoted_signup = await _try_promote_bench(event_id, existing["role_id"], conn)
            else:
                row = await conn.fetchrow(
                    "SELECT COALESCE(MAX(signup_order), 0) + 1 AS next_order FROM event_signups WHERE event_id = $1",
                    event_id
                )
                await conn.execute(
                    """INSERT INTO event_signups
                       (event_id, discord_id, discord_name, role_id, role_name, bdo_class, signup_order, status)
                       VALUES ($1, $2, $3, $4, $5, $6, $7, $8)""",
                    event_id, discord_id, discord_name, role_id, role_name, bdo_class, row["next_order"], status,
                )
            await conn.execute("UPDATE events SET updated_at = NOW() WHERE id = $1", event_id)
    await _sync_calendar_interest(event_id, discord_id, add=(status not in ("absent", "declined")))
    bench_position = None
    if status == "bench":
        bench_position = await utils.pool.fetchval(
            """SELECT COUNT(*)::int FROM event_signups
               WHERE event_id = $1 AND status = 'bench'
               AND signup_order <= (
                   SELECT signup_order FROM event_signups WHERE event_id = $1 AND discord_id = $2
               )""",
            event_id, discord_id,
        )
    return status, bench_position, promoted_signup


async def _is_event_open(event_id: str) -> tuple[bool, str]:
    """Returns (open, reason). open=False means signups should be rejected."""
    event = await fetch_event(event_id)
    if not event:
        return False, "Event not found."
    if event.get("status") != "active":
        return False, "Signups are closed for this event."
    # Check if the event datetime has passed
    if event.get("event_date") and event.get("event_time"):
        try:
            tz_str   = event.get("event_timezone") or "UTC"
            date_s   = str(event["event_date"])[:10]
            time_s   = str(event["event_time"])[:5]
            dt_naive = datetime.strptime(f"{date_s} {time_s}", "%Y-%m-%d %H:%M")
            dt_aware = dt_naive.replace(tzinfo=ZoneInfo(tz_str))
            if dt_aware < datetime.now(timezone.utc):
                return False, "This event has already passed — signups are closed."
        except Exception:
            pass
    return True, ""


# ── Class selection views ──────────────────────────────────────────────────────

class ClassSelectMenu1(discord.ui.Select):
    def __init__(self, event_id: str, role_id, role_name: str):
        self.event_id  = event_id
        self.role_id   = role_id
        self.role_name = role_name
        options = [discord.SelectOption(label=c, value=c) for c in BDO_CLASSES_1]
        super().__init__(placeholder="Classes A–V…", options=options, custom_id=f"cls1:{event_id}:{role_id}")

    async def callback(self, interaction: discord.Interaction):
        await _finish_signup(interaction, self.event_id, self.role_id, self.role_name, self.values[0])


class ClassSelectMenu2(discord.ui.Select):
    def __init__(self, event_id: str, role_id, role_name: str):
        self.event_id  = event_id
        self.role_id   = role_id
        self.role_name = role_name
        options = [discord.SelectOption(label=c, value=c) for c in BDO_CLASSES_2]
        super().__init__(placeholder="Classes W…", options=options, custom_id=f"cls2:{event_id}:{role_id}")

    async def callback(self, interaction: discord.Interaction):
        await _finish_signup(interaction, self.event_id, self.role_id, self.role_name, self.values[0])


class ClassSelectView(discord.ui.View):
    """Class selection with optional profile quick-pick buttons."""

    def __init__(self, event_id: str, role_id, role_name: str, profile_classes: list[str] | None = None):
        super().__init__(timeout=120)

        # Green quick-pick buttons for saved profile classes (up to 2)
        for cls in (profile_classes or [])[:2]:
            btn = discord.ui.Button(
                label=cls,
                style=discord.ButtonStyle.success,
                custom_id=f"qpick:{event_id}:{role_id}:{cls}",
            )
            btn.callback = self._make_quick_cb(event_id, role_id, role_name, cls)
            self.add_item(btn)

        self.add_item(ClassSelectMenu1(event_id, role_id, role_name))
        self.add_item(ClassSelectMenu2(event_id, role_id, role_name))

    @staticmethod
    def _make_quick_cb(event_id, role_id, role_name, bdo_class):
        async def callback(interaction: discord.Interaction):
            await _finish_signup(interaction, event_id, role_id, role_name, bdo_class)
        return callback


async def _finish_signup(interaction: discord.Interaction, event_id: str, role_id, role_name: str, bdo_class: str):
    try:
        resolved, bench_pos, promoted = await _upsert_signup(
            event_id, str(interaction.user.id), interaction.user.display_name,
            role_id, role_name, bdo_class, "accepted",
        )
        if resolved == "bench":
            msg = f"🪑 Added to **bench** as **{bdo_class}** for **{role_name}** — the role or event is full."
            pos_str = f" You're **#{bench_pos} on the bench**." if bench_pos else ""
            try:
                dm_user = await interaction.client.fetch_user(int(str(interaction.user.id)))
                await dm_user.send(
                    f"🪑 You've been added to the bench for **{event.get('title', 'an event') if (event := await fetch_event(event_id)) else 'an event'}**.\n"
                    f"The **{role_name}** role or event is at capacity.{pos_str}\n"
                    f"If someone withdraws, you may be automatically promoted.\n"
                    f"{WEBSITE_URL}/#/calendar?tab=events&event={event_id}"
                )
            except Exception:
                pass
        else:
            msg = f"✅ Signed up as **{bdo_class}** for **{role_name}**!"
        if promoted:
            try:
                dm_promoted = await interaction.client.fetch_user(int(promoted["discord_id"]))
                ev_title = (await fetch_event(event_id) or {}).get("title", "an event")
                await dm_promoted.send(
                    f"✅ A spot opened up for **{ev_title}**!\n"
                    f"You've been moved from the bench to **{promoted.get('role_name') or 'an available role'}**.\n"
                    f"{WEBSITE_URL}/#/calendar?tab=events&event={event_id}"
                )
            except Exception:
                pass
        await interaction.response.edit_message(content=msg, view=None)
        event = await fetch_event(event_id)
        if event and event.get("message_id") and event.get("channel_id"):
            try:
                channel = interaction.client.get_channel(int(event["channel_id"]))
                if channel is None:
                    channel = await interaction.client.fetch_channel(int(event["channel_id"]))
                msg = await channel.fetch_message(int(event["message_id"]))
                await _refresh_embed(msg, event_id)
            except Exception as e:
                print(f"[events] embed refresh failed: {e}")
    except Exception as e:
        try:
            await interaction.response.edit_message(content=f"Something went wrong: {e}", view=None)
        except Exception:
            await interaction.followup.send(f"Something went wrong: {e}", ephemeral=True)


# ── Main signup view ───────────────────────────────────────────────────────────

class EventSignupView(discord.ui.View):
    """Persistent view attached to an event embed."""

    def __init__(self, event_id: str, roles: list, status: str = "active"):
        super().__init__(timeout=None)
        self.event_id = event_id

        if status != "active":
            self.add_item(discord.ui.Button(
                label="🔒 Signups Closed",
                style=discord.ButtonStyle.secondary,
                custom_id=f"closed_info:{event_id}",
                disabled=True,
            ))
        else:
            for role in roles:
                cap   = role.get("soft_cap")
                label = role["name"] + (f" ({cap})" if cap else "")
                btn   = discord.ui.Button(
                    label=label,
                    style=discord.ButtonStyle.primary,
                    custom_id=f"signup:{event_id}:{role['id']}",
                    emoji=role.get("emoji") or None,
                )
                btn.callback = self._make_signup_cb(role["id"], role["name"])
                self.add_item(btn)

            for label, status, emoji_str, cid_prefix in [
                ("Tentative", "tentative", "❓", "tentative"),
                ("Declined",  "declined",  "❌", "declined"),
            ]:
                btn = discord.ui.Button(
                    label=label, style=discord.ButtonStyle.secondary,
                    custom_id=f"{cid_prefix}:{event_id}", emoji=emoji_str,
                )
                btn.callback = self._make_status_cb(status)
                self.add_item(btn)

            withdraw_btn = discord.ui.Button(
                label="Withdraw", style=discord.ButtonStyle.danger,
                custom_id=f"withdraw:{event_id}",
            )
            withdraw_btn.callback = self._withdraw_cb
            self.add_item(withdraw_btn)

            close_btn = discord.ui.Button(
                label="Close Signups", style=discord.ButtonStyle.secondary,
                custom_id=f"close_signups:{event_id}", emoji="🔒",
            )
            close_btn.callback = self._close_signups_cb
            self.add_item(close_btn)

        self.add_item(discord.ui.Button(
            label="View on Website",
            style=discord.ButtonStyle.link,
            url=f"{WEBSITE_URL}/#/calendar?tab=events&event={event_id}",
        ))

    def _make_signup_cb(self, role_id, role_name: str):
        async def callback(interaction: discord.Interaction):
            open_, reason = await _is_event_open(self.event_id)
            if not open_:
                await interaction.response.send_message(f"🔒 {reason}", ephemeral=True)
                return

            # Validate role still exists
            role_row = await utils.pool.fetchrow(
                "SELECT id FROM event_roles WHERE id = $1", role_id
            )
            if not role_row:
                await interaction.response.send_message(
                    "⚠️ That role no longer exists. The event may have been updated.", ephemeral=True
                )
                return

            row = await utils.pool.fetchrow(
                "SELECT bdo_class, alt_class FROM users WHERE discord_id = $1",
                str(interaction.user.id),
            )
            profile_classes = []
            if row:
                if row["bdo_class"]:
                    profile_classes.append(row["bdo_class"])
                if row["alt_class"] and row["alt_class"] != row["bdo_class"]:
                    profile_classes.append(row["alt_class"])

            content = f"Choose your class for **{role_name}**:"
            if profile_classes:
                content += "\n\n**Quick pick** (from your profile) — or use the dropdowns below:"

            await interaction.response.send_message(
                content,
                view=ClassSelectView(self.event_id, role_id, role_name, profile_classes),
                ephemeral=True,
            )
        return callback

    async def _fetch_embed_msg(self, client: discord.Client):
        """Fetch the event's Discord message via DB so we don't rely on interaction.message."""
        event = await fetch_event(self.event_id)
        if not event or not event.get("message_id") or not event.get("channel_id"):
            return None
        try:
            ch = client.get_channel(int(event["channel_id"]))
            if ch is None:
                ch = await client.fetch_channel(int(event["channel_id"]))
            return await ch.fetch_message(int(event["message_id"]))
        except Exception as e:
            print(f"[events] could not fetch embed message: {e}")
            return None

    def _make_status_cb(self, status: str):
        async def callback(interaction: discord.Interaction):
            await interaction.response.defer(ephemeral=True)
            open_, reason = await _is_event_open(self.event_id)
            if not open_:
                await interaction.followup.send(f"🔒 {reason}", ephemeral=True)
                return
            try:
                await _upsert_signup(
                    self.event_id, str(interaction.user.id), interaction.user.display_name,
                    None, None, None, status,
                )
                await interaction.followup.send(f"Marked as **{status.capitalize()}**.", ephemeral=True)
                msg = await self._fetch_embed_msg(interaction.client)
                await _refresh_embed(msg, self.event_id)
            except Exception as e:
                await interaction.followup.send(f"Something went wrong: {e}", ephemeral=True)
        return callback

    async def _withdraw_cb(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        open_, reason = await _is_event_open(self.event_id)
        if not open_:
            await interaction.followup.send(f"🔒 {reason}", ephemeral=True)
            return
        try:
            async with utils.pool.acquire() as conn:
                async with conn.transaction():
                    old = await conn.fetchrow(
                        "SELECT role_id, status FROM event_signups WHERE event_id = $1 AND discord_id = $2",
                        self.event_id, str(interaction.user.id),
                    )
                    await conn.execute(
                        "DELETE FROM event_signups WHERE event_id = $1 AND discord_id = $2",
                        self.event_id, str(interaction.user.id),
                    )
                    await conn.execute("UPDATE events SET updated_at = NOW() WHERE id = $1", self.event_id)
                    promoted_from_bench = None
                    if old and old["status"] == "accepted":
                        promoted_from_bench = await _try_promote_bench(self.event_id, old["role_id"], conn)
            await _sync_calendar_interest(self.event_id, str(interaction.user.id), add=False)
            if promoted_from_bench:
                try:
                    ev_title = (await fetch_event(self.event_id) or {}).get("title", "an event")
                    dm_user = await interaction.client.fetch_user(int(promoted_from_bench["discord_id"]))
                    await dm_user.send(
                        f"✅ A spot opened up for **{ev_title}**!\n"
                        f"You've been moved from the bench to **{promoted_from_bench.get('role_name') or 'an available role'}**.\n"
                        f"{WEBSITE_URL}/#/calendar?tab=events&event={self.event_id}"
                    )
                except Exception:
                    pass
            await interaction.followup.send("Withdrawn from event.", ephemeral=True)
            msg = await self._fetch_embed_msg(interaction.client)
            await _refresh_embed(msg, self.event_id)
        except Exception as e:
            await interaction.followup.send(f"Something went wrong: {e}", ephemeral=True)

    async def _close_signups_cb(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.manage_events:
            await interaction.response.send_message("❌ You don't have permission to close signups.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        try:
            await utils.pool.execute(
                "UPDATE events SET status = 'closed', updated_at = NOW() WHERE id = $1",
                self.event_id,
            )
            await interaction.followup.send("🔒 Signups have been closed.", ephemeral=True)
            msg = await self._fetch_embed_msg(interaction.client)
            await _refresh_embed(msg, self.event_id)
        except Exception as e:
            await interaction.followup.send(f"Something went wrong: {e}", ephemeral=True)


# ── Cog ────────────────────────────────────────────────────────────────────────

class EventsCog(commands.Cog, name="Events"):

    def __init__(self, bot):
        self.bot = bot
        self._listen_conn: asyncpg.Connection | None = None
        self.event_reminder.start()
        self.new_embed_poller.start()
        self._close_tasks: dict[str, asyncio.Task] = {}

    def cog_unload(self):
        self.event_reminder.cancel()
        self.new_embed_poller.cancel()
        for task in self._close_tasks.values():
            task.cancel()
        if self._listen_conn:
            import asyncio
            asyncio.ensure_future(self._listen_conn.close())

    async def cog_load(self):
        # Restore views synchronously here — pool is available and add_view
        # works before the bot connects, so no need to wait_until_ready.
        await self._restore_views()
        # Listener needs an active gateway connection, so defer it.
        import asyncio
        asyncio.ensure_future(self._start_listener())

    async def _restore_views(self):
        """Re-register persistent views and schedule auto-close tasks on startup."""
        import json as _json
        rows = await utils.pool.fetch("""
            SELECT e.id, e.status, e.message_id,
                   e.event_date, e.event_time, e.event_timezone,
                json_agg(
                    json_build_object('id', er.id, 'name', er.name, 'emoji', er.emoji,
                                      'soft_cap', er.soft_cap, 'display_order', er.display_order)
                    ORDER BY er.display_order
                ) FILTER (WHERE er.id IS NOT NULL) AS roles
            FROM events e
            LEFT JOIN event_roles er ON er.event_id = e.id
            WHERE e.status IN ('active', 'closed') AND e.message_id IS NOT NULL
            GROUP BY e.id
        """)
        count = 0
        for row in rows:
            try:
                event_id   = str(row["id"])
                message_id = int(row["message_id"])
                roles_raw  = row["roles"] or []
                if isinstance(roles_raw, str):
                    roles_raw = _json.loads(roles_raw)
                roles = [r for r in roles_raw if r]
                self.bot.add_view(
                    EventSignupView(event_id, roles, status=str(row["status"])),
                    message_id=message_id,
                )
                self._schedule_close(dict(row))
                count += 1
            except Exception as e:
                print(f"[events] failed to restore view for event {row.get('id')}: {e}")
        print(f"[events] restored {count} persistent view(s)")

    # ── Calendar reminder loop (unchanged) ────────────────────────────────────

    @tasks.loop(minutes=1)
    async def event_reminder(self):
        try:
            now = datetime.now(timezone.utc)
            for guild in self.bot.guilds:
                remind_channel = discord.utils.get(guild.text_channels, name=utils.NOTIFY_CHANNEL)

                if remind_channel:
                    for event in await guild.fetch_scheduled_events():
                        try:
                            if event.status != discord.EventStatus.scheduled:
                                continue
                            interested = [u async for u in event.users()]
                            mentions   = " ".join(u.mention for u in interested)
                            thirty = event.start_time - timedelta(minutes=30)
                            five   = event.start_time - timedelta(minutes=5)
                            if thirty <= now < thirty + timedelta(minutes=1):
                                await remind_channel.send(f"Reminder! {event.name} starts in 30 minutes! {event.url}\n{mentions}")
                            elif five <= now < five + timedelta(minutes=1):
                                await remind_channel.send(f"Reminder! {event.name} starts in 5 minutes! {event.url}\n{mentions}")
                        except Exception as e:
                            print(f"Error processing event {event.id}: {e}")

                try:
                    for minutes_ahead in [30, 5]:
                        window_start = now + timedelta(minutes=minutes_ahead)
                        window_end   = window_start + timedelta(minutes=1)
                        cal_events   = await utils.pool.fetch("""
                            SELECT ce.title,
                                   array_agg(u.discord_id) FILTER (WHERE u.discord_id IS NOT NULL) AS discord_ids
                            FROM calendar_events ce
                            LEFT JOIN calendar_event_interests cei ON cei.event_id = ce.id
                            LEFT JOIN users u ON u.id = cei.user_id
                            LEFT JOIN events ev ON ev.calendar_event_id = ce.id
                            WHERE ce.event_time IS NOT NULL AND ce.event_timezone IS NOT NULL
                              AND (ev.id IS NULL OR ev.enable_reminder_ping = TRUE)
                            GROUP BY ce.id, ce.title
                            HAVING (ce.event_date + ce.event_time) AT TIME ZONE ce.event_timezone BETWEEN $1 AND $2
                        """, window_start, window_end)
                        rc = discord.utils.get(guild.text_channels, name=utils.NOTIFY_CHANNEL)
                        if not rc:
                            continue
                        for ev in cal_events:
                            mentions = " ".join(
                                m.mention for did in (ev['discord_ids'] or [])
                                if did and (m := guild.get_member(int(did)))
                            )
                            msg = f"Reminder! {ev['title']} starts in {minutes_ahead} minutes!"
                            if mentions:
                                msg += f"\n{mentions}"
                            await rc.send(msg)
                except Exception as e:
                    print(f"Error checking calendar reminders: {e}")
        except Exception as e:
            print(f"Error in event_reminder loop: {e}")

    @event_reminder.before_loop
    async def before_event_reminder(self):
        await self.bot.wait_until_ready()

    # ── Auto-close via asyncio tasks ─────────────────────────────────────────

    def _schedule_close(self, event: dict):
        """Schedule (or cancel) an exact-time close task for an event."""
        event_id = str(event['id'])
        existing = self._close_tasks.pop(event_id, None)
        if existing and not existing.done():
            existing.cancel()

        if event.get('status') != 'active':
            return
        if not event.get('event_date') or not event.get('event_time'):
            return

        try:
            tz_str   = event.get('event_timezone') or 'UTC'
            date_s   = str(event['event_date'])[:10]
            time_s   = str(event['event_time'])[:5]
            dt_naive = datetime.strptime(f"{date_s} {time_s}", "%Y-%m-%d %H:%M")
            start_dt = dt_naive.replace(tzinfo=ZoneInfo(tz_str))
            delay    = (start_dt - datetime.now(timezone.utc)).total_seconds()
        except Exception as e:
            print(f"[events] could not compute close time for {event_id}: {e}")
            return

        self._close_tasks[event_id] = asyncio.create_task(self._close_after(event_id, delay))

    async def _close_after(self, event_id: str, delay: float):
        try:
            if delay > 0:
                print(f"[events] auto-close scheduled for {event_id} in {delay/3600:.2f}h")
                await asyncio.sleep(delay)
            row = await utils.pool.fetchrow(
                "SELECT status FROM events WHERE id = $1", event_id
            )
            if not row or row['status'] != 'active':
                return
            await utils.pool.execute(
                "UPDATE events SET status = 'closed', updated_at = NOW() WHERE id = $1",
                event_id,
            )
            await utils.pool.execute("SELECT pg_notify('event_updated', $1)", event_id)
            print(f"[events] auto-closed event {event_id}")
        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"[events] auto-close error for {event_id}: {e}")

    # ── LISTEN/NOTIFY handler ─────────────────────────────────────────────────

    async def _start_listener(self):
        import asyncio
        await self.bot.wait_until_ready()
        while True:
            try:
                self._listen_conn = await asyncpg.connect(os.getenv("DATABASE_URL"))
                await self._listen_conn.add_listener("event_updated",  self._on_event_notify)
                await self._listen_conn.add_listener("signup_changed", self._on_signup_notify)
                print("[events] LISTEN connection established")
                # asyncpg Connection has no wait_closed() — poll is_closed() instead
                while not self._listen_conn.is_closed():
                    await asyncio.sleep(10)
                print("[events] LISTEN connection closed — reconnecting")
            except Exception as e:
                print(f"[events] LISTEN connection error: {e} — reconnecting in 5s")
            finally:
                if self._listen_conn and not self._listen_conn.is_closed():
                    await self._listen_conn.close()
            await asyncio.sleep(5)

    async def _on_signup_notify(self, conn, pid, channel, payload: str):
        try:
            import json as _json
            data = _json.loads(payload)
            discord_id = data.get("discord_id")
            if not discord_id:
                return
            event_id    = data.get("event_id", "")
            event_title = data.get("event_title", "an event")
            old_status  = data.get("old_status")
            new_status  = data.get("new_status")
            old_role    = data.get("old_role")
            new_role    = data.get("new_role")

            lines = [f"📋 Your signup for **{event_title}** was updated by an officer."]
            if old_status != new_status and new_status:
                lines.append(f"Status: **{old_status or '—'}** → **{new_status}**")
            if old_role != new_role:
                lines.append(f"Role: **{old_role or 'None'}** → **{new_role or 'None'}**")
            lines.append(f"{WEBSITE_URL}/#/calendar?tab=events&event={event_id}")

            try:
                user_obj = await self.bot.fetch_user(int(discord_id))
                await user_obj.send("\n".join(lines))
            except Exception:
                pass
        except Exception as e:
            print(f"[events] signup_changed notify error: {e}")

    async def _on_event_notify(self, conn, pid, channel, event_id: str):
        try:
            event = await fetch_event(event_id)
            if not event:
                return
            roles   = await fetch_roles(event_id)
            signups = await fetch_signups(event_id)
            emojis  = await fetch_class_emojis()

            if not event.get("message_id"):
                # Not yet posted — post it now
                await self._post_signup_embed(event)
                self._schedule_close(event)
                return

            channel_obj = self.bot.get_channel(int(event["channel_id"]))
            if channel_obj is None:
                channel_obj = await self.bot.fetch_channel(int(event["channel_id"]))
            msg = await channel_obj.fetch_message(int(event["message_id"]))

            embed = await build_event_embed(event, roles, signups, emojis)
            view  = EventSignupView(event_id, roles, status=event.get("status", "active"))
            await msg.edit(embed=embed, view=view)
            self._schedule_close(event)
        except Exception as e:
            print(f"[events] notify handler error for {event_id}: {e}")

    # ── New-embed poller (fallback for events without a message yet) ──────────

    @tasks.loop(minutes=1)
    async def new_embed_poller(self):
        try:
            # Post embeds not yet sent
            rows = await utils.pool.fetch("""
                SELECT * FROM events
                WHERE status = 'active' AND message_id IS NULL AND channel_id IS NOT NULL
            """)
            for row in rows:
                await self._post_signup_embed(dict(row))

            # Refresh embeds for recurring occurrences that have no roles but the series does
            roleless = await utils.pool.fetch("""
                SELECT e.*
                FROM events e
                JOIN recurring_events r ON r.id = e.recurring_id
                WHERE e.status = 'active'
                  AND e.message_id IS NOT NULL
                  AND e.channel_id IS NOT NULL
                  AND NOT EXISTS (SELECT 1 FROM event_roles er WHERE er.event_id = e.id)
                  AND (
                        (jsonb_typeof(r.roles) = 'array' AND jsonb_array_length(r.roles) > 0)
                        OR jsonb_typeof(r.roles) = 'string'
                      )
            """)
            for row in roleless:
                event = dict(row)
                event_id = str(event["id"])
                series_roles = await utils.pool.fetch(
                    "SELECT roles FROM recurring_events WHERE id = $1", event["recurring_id"]
                )
                if not series_roles:
                    continue
                raw = series_roles[0]["roles"]
                if isinstance(raw, str):
                    try:
                        import json as _j; raw = _j.loads(raw)
                    except Exception:
                        continue
                if not isinstance(raw, list):
                    continue
                for i, r in enumerate(raw):
                    if not isinstance(r, dict) or not r.get("name"):
                        continue
                    sc = r.get("soft_cap")
                    await utils.pool.execute("""
                        INSERT INTO event_roles (event_id, name, emoji, soft_cap, display_order)
                        VALUES ($1, $2, $3, $4, $5)
                        ON CONFLICT DO NOTHING
                    """, event_id, r["name"], r.get("emoji"), int(sc) if sc is not None else None, i)
                print(f"[events] repaired missing roles for occurrence {event_id}")
                await utils.pool.execute("SELECT pg_notify('event_updated', $1)", event_id)
        except Exception as e:
            print(f"[events] new-embed poller error: {e}")

    @new_embed_poller.before_loop
    async def before_new_embed_poller(self):
        await self.bot.wait_until_ready()

    async def _post_signup_embed(self, event: dict):
        event_id   = str(event["id"])
        channel_id = event.get("channel_id")

        channel = self.bot.get_channel(int(channel_id))
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(int(channel_id))
            except Exception as e:
                print(f"[events] could not fetch channel {channel_id}: {e}")
                return

        # Always fetch roles from DB — don't rely on the event dict having them
        roles   = await fetch_roles(event_id)
        signups = await fetch_signups(event_id)
        emojis  = await fetch_class_emojis()
        embed   = await build_event_embed(event, roles, signups, emojis)
        view    = EventSignupView(event_id, roles, status=event.get("status", "active"))

        content = None
        if event.get("enable_ping", True) and event.get("ping_role_ids"):
            mentions = " ".join(f"<@&{rid}>" for rid in event["ping_role_ids"] if rid)
            if mentions:
                content = mentions
        msg = await channel.send(content=content, embed=embed, view=view)

        await utils.pool.execute(
            "UPDATE events SET message_id = $1, updated_at = NOW() WHERE id = $2",
            str(msg.id), event_id,
        )

    # ── Commands ──────────────────────────────────────────────────────────────

    @commands.command()
    @commands.has_permissions(manage_events=True)
    async def create_event(self, ctx, name: str, description: str, start_time_str: str, duration_minutes: int):
        """Creates a Discord scheduled event."""
        try:
            start_time = utils.parse_discord_timestamp(start_time_str)
            if start_time is None:
                try:
                    start_time = datetime.fromisoformat(start_time_str)
                except ValueError:
                    await ctx.send("Invalid time format. Use `<t:unix_timestamp:F>` or ISO format.")
                    return
            end_time = start_time + timedelta(minutes=duration_minutes)
            await ctx.guild.create_scheduled_event(
                name=name, description=description,
                start_time=start_time, end_time=end_time,
                entity_type=discord.EntityType.external,
                location="BDO",
                privacy_level=discord.PrivacyLevel.guild_only,
            )
            await ctx.send(f'Event "{name}" created!')
        except Exception as e:
            await ctx.send(f"An error occurred: {e}")


async def setup(bot):
    await bot.add_cog(EventsCog(bot))
