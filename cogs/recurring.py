import discord, asyncio, asyncpg, os, json as _json, traceback
from discord.ext import commands
from datetime import datetime, timedelta, timezone, date, time as dt_time
from zoneinfo import ZoneInfo
import utils


class RecurringCog(commands.Cog, name="Recurring"):

    def __init__(self, bot):
        self.bot = bot
        self._tasks: dict[str, asyncio.Task] = {}
        self._listen_conn = None

    async def cog_load(self):
        asyncio.ensure_future(self._schedule_all())
        asyncio.ensure_future(self._start_listener())

    async def cog_unload(self):
        for task in self._tasks.values():
            task.cancel()
        if self._listen_conn and not self._listen_conn.is_closed():
            await self._listen_conn.close()

    # ── Scheduling ────────────────────────────────────────────────────────────

    async def _schedule_all(self):
        await self.bot.wait_until_ready()
        today = datetime.now(timezone.utc).date()
        rows = await utils.pool.fetch("""
            SELECT * FROM recurring_events
            WHERE (end_date IS NULL OR end_date >= $1)
        """, today)
        for row in rows:
            self._schedule_series(dict(row))
        print(f"[recurring] scheduled {len(rows)} series on startup")

    def _schedule_series(self, series: dict):
        sid = str(series['id'])
        existing = self._tasks.get(sid)
        if existing and not existing.done():
            existing.cancel()
        self._tasks[sid] = asyncio.create_task(self._run_series(sid))

    def _cancel_series_task(self, sid: str):
        task = self._tasks.pop(sid, None)
        if task and not task.done():
            task.cancel()

    # ── Next-occurrence logic ─────────────────────────────────────────────────

    def _compute_next_event_dt(self, series: dict, after: datetime) -> datetime | None:
        """Returns the next event datetime (UTC) strictly after `after`, valid per series rules."""
        try:
            tz = ZoneInfo(series.get('event_timezone') or 'UTC')
            time_s = str(series['event_time'])[:5]
            h, m = int(time_s[:2]), int(time_s[3:5])
            weekdays = set(series.get('weekdays') or [])

            def _to_date(v):
                if v is None:
                    return None
                if isinstance(v, date):
                    return v
                return date.fromisoformat(str(v)[:10])

            end_date   = _to_date(series.get('end_date'))
            start_date = _to_date(series.get('start_date'))

            skip_dates = set()
            for sd in (series.get('skip_dates') or []):
                d = _to_date(sd)
                if d:
                    skip_dates.add(d)
        except Exception as e:
            print(f"[recurring] config parse error: {e}")
            return None

        # Build candidate from 'after' in local time
        after_local = after.astimezone(tz)
        candidate = after_local.replace(hour=h, minute=m, second=0, microsecond=0)
        if candidate <= after_local:
            candidate = (after_local + timedelta(days=1)).replace(hour=h, minute=m, second=0, microsecond=0)

        for _ in range(400):
            d = candidate.date()
            if start_date and d < start_date:
                candidate = (candidate + timedelta(days=1)).replace(hour=h, minute=m, second=0, microsecond=0)
                continue
            if end_date and d > end_date:
                return None
            if candidate.weekday() in weekdays and d not in skip_dates:
                return candidate.astimezone(timezone.utc)
            candidate = (candidate + timedelta(days=1)).replace(hour=h, minute=m, second=0, microsecond=0)

        return None

    # ── Per-series task ───────────────────────────────────────────────────────

    async def _run_series(self, sid: str):
        try:
            while True:
                row = await utils.pool.fetchrow(
                    "SELECT * FROM recurring_events WHERE id = $1", sid
                )
                if not row:
                    return
                series = dict(row)

                now = datetime.now(timezone.utc)
                next_event_dt = self._compute_next_event_dt(series, after=now)
                if next_event_dt is None:
                    print(f"[recurring] series {sid}: no future occurrences, retiring")
                    return

                tz_name = series.get('event_timezone') or 'UTC'
                tz = ZoneInfo(tz_name)
                occurrence_date = next_event_dt.astimezone(tz).date()

                # Skip if already posted (handles restarts / duplicate protection)
                existing = await utils.pool.fetchrow(
                    "SELECT id FROM events WHERE recurring_id = $1 AND event_date = $2",
                    sid, occurrence_date,
                )
                if existing:
                    next_event_dt = self._compute_next_event_dt(
                        series, after=next_event_dt + timedelta(seconds=1)
                    )
                    if next_event_dt is None:
                        return
                    occurrence_date = next_event_dt.astimezone(tz).date()

                advance_minutes = int(series.get('advance_minutes') or 2880)
                post_dt = next_event_dt - timedelta(minutes=advance_minutes)
                delay = (post_dt - datetime.now(timezone.utc)).total_seconds()

                if delay > 0:
                    print(f"[recurring] series {sid}: sleeping {delay/3600:.2f}h → post {occurrence_date}")
                    await asyncio.sleep(delay)
                else:
                    print(f"[recurring] series {sid}: post time passed, posting {occurrence_date} now")

                # Re-check validity after sleep (series may have been edited)
                row2 = await utils.pool.fetchrow(
                    "SELECT end_date, skip_dates FROM recurring_events WHERE id = $1",
                    sid,
                )
                if not row2:
                    return
                def _to_date(v):
                    if v is None: return None
                    if isinstance(v, date): return v
                    return date.fromisoformat(str(v)[:10])
                end_date = _to_date(row2['end_date'])
                if end_date and occurrence_date > end_date:
                    return
                skip_dates = set(_to_date(d) for d in (row2['skip_dates'] or []))
                if occurrence_date in skip_dates:
                    continue  # skip, loop back to find next

                await self._create_occurrence(series, next_event_dt, occurrence_date)

        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"[recurring] series {sid} error: {e}")
            traceback.print_exc()

    async def _create_occurrence(self, series: dict, event_dt: datetime, occurrence_date: date):
        sid    = str(series['id'])
        title  = series['title']
        tz_str = series.get('event_timezone') or 'UTC'
        time_s = str(series['event_time'])[:5]
        event_time_obj = dt_time(int(time_s[:2]), int(time_s[3:5]))

        roles_raw = series.get('roles') or []
        if isinstance(roles_raw, str):
            roles_raw = _json.loads(roles_raw)
        # Normalize: each element must be a dict (double-encoded JSONB yields strings)
        normalized = []
        for r in roles_raw:
            if isinstance(r, dict):
                normalized.append(r)
            elif isinstance(r, str):
                try:
                    parsed = _json.loads(r)
                    if isinstance(parsed, dict):
                        normalized.append(parsed)
                except Exception:
                    pass
        roles_raw = normalized

        try:
            async with utils.pool.acquire() as conn:
                async with conn.transaction():
                    event_row = await conn.fetchrow("""
                        INSERT INTO events
                          (title, description, event_date, event_time, event_timezone,
                           total_cap, channel_id, status, recurring_id, created_by,
                           ping_role_ids, enable_ping, enable_reminder_ping)
                        VALUES ($1, $2, $3, $4, $5, $6, $7, 'active', $8, $9, $10, $11, $12)
                        RETURNING *
                    """,
                        title,
                        series.get('description'),
                        occurrence_date,
                        event_time_obj,
                        tz_str,
                        int(series['total_cap']) if series.get('total_cap') is not None else None,
                        series.get('channel_id'),
                        sid,
                        series.get('created_by'),
                        series.get('ping_role_ids') or [],
                        series.get('enable_ping', True),
                        series.get('enable_reminder_ping', True),
                    )
                    event_id = str(event_row['id'])

                    for i, r in enumerate(roles_raw):
                        if not r.get('name'):
                            continue
                        sc = r.get('soft_cap')
                        await conn.execute("""
                            INSERT INTO event_roles (event_id, name, emoji, soft_cap, display_order)
                            VALUES ($1, $2, $3, $4, $5)
                        """, event_id, r['name'], r.get('emoji'), int(sc) if sc is not None else None, i)

                    cal = await conn.fetchrow("""
                        INSERT INTO calendar_events
                          (title, description, event_date, event_time, event_timezone, created_by)
                        VALUES ($1, $2, $3, $4, $5, $6)
                        RETURNING id
                    """, title, series.get('description'), occurrence_date, event_time_obj, tz_str, series.get('created_by'))
                    await conn.execute(
                        "UPDATE events SET calendar_event_id = $1 WHERE id = $2",
                        cal['id'], event_id,
                    )

            await utils.pool.execute("SELECT pg_notify('event_updated', $1)", event_id)
            print(f"[recurring] created event {event_id} for series {sid} on {occurrence_date}")

        except Exception as e:
            print(f"[recurring] failed to create occurrence for {sid}: {e}")
            import traceback; traceback.print_exc()

    # ── pg_notify listener ────────────────────────────────────────────────────

    async def _start_listener(self):
        await self.bot.wait_until_ready()
        while True:
            try:
                self._listen_conn = await asyncpg.connect(os.getenv("DATABASE_URL"))
                await self._listen_conn.add_listener("recurring_updated", self._on_recurring_notify)
                print("[recurring] LISTEN connection established")
                while not self._listen_conn.is_closed():
                    await asyncio.sleep(10)
                print("[recurring] LISTEN connection closed — reconnecting")
            except Exception as e:
                print(f"[recurring] LISTEN error: {e} — reconnecting in 5s")
            finally:
                if self._listen_conn and not self._listen_conn.is_closed():
                    await self._listen_conn.close()
            await asyncio.sleep(5)

    async def _on_recurring_notify(self, conn, pid, channel, sid: str):
        try:
            row = await utils.pool.fetchrow(
                "SELECT * FROM recurring_events WHERE id = $1", sid
            )
            if not row:
                self._cancel_series_task(sid)
                print(f"[recurring] series {sid} deleted, task cancelled")
                return

            today = datetime.now(timezone.utc).date()
            def _to_date(v):
                if v is None: return None
                if isinstance(v, date): return v
                return date.fromisoformat(str(v)[:10])
            end_date = _to_date(row.get('end_date'))
            if end_date and end_date < today:
                self._cancel_series_task(sid)
                print(f"[recurring] series {sid} ended, task cancelled")
                return

            self._schedule_series(dict(row))
            print(f"[recurring] series {sid} rescheduled via notify")
        except Exception as e:
            print(f"[recurring] notify error for {sid}: {e}")


async def setup(bot):
    await bot.add_cog(RecurringCog(bot))
