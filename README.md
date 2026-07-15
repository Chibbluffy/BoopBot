# BoopBot


## Setup
1. Create a service file:
```bash
sudo nano /etc/systemd/system/boopbot.service
```
2. Paste this in (adjust paths as needed):
```INI
[Unit]
Description=BoopBot Discord Bot
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/BoopBot
ExecStart=/usr/bin/python3 -u /home/ubuntu/BoopBot/bot.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```
> The `-u` flag on `python3` disables output buffering so `print()` logs appear immediately in `journalctl`.

3. Copy `.env.example` to `.env` and fill in the values:
```bash
cp .env.example .env
nano .env
```

4. Enable and start it:
```bash
sudo systemctl daemon-reload
sudo systemctl enable boopbot
sudo systemctl start boopbot
```

Useful commands going forward:
```bash
sudo systemctl status boopbot    # check if it's running
sudo systemctl stop boopbot      # stop the bot
sudo systemctl restart boopbot   # restart the bot
journalctl -u boopbot -f         # view live logs
journalctl -u boopbot -n 50      # view last 50 log lines
```

## Configuration

### `.env`
| Variable | Description |
|---|---|
| `BOT_TOKEN` | Discord bot token |
| `CHEST_INFO_CHANNEL_ID` | Channel ID for chest timer display message |
| `CHEST_INFO_MESSAGE_ID` | Message ID for chest timer display message |
| `CHEST_EVENTS_FILE` | Path to chest events JSON file (default: `chest_events.json`) |
| `DATABASE_URL` | PostgreSQL connection string (e.g. `postgres://boop:password@localhost:5432/boopfish`) |
| `BRAIN_BASE_URL` | Base URL of the `boop-brain` chat/orchestration service (default: `http://10.8.0.200:8000`) |
| `BRAIN_SHARED_SECRET` | Shared secret sent as `X-BoopBot-Secret` — must match `BRAIN_SHARED_SECRET` on the `boop-brain` service |
| `JUMPIN_PROBABILITY` | Chance (0–1) the bot jumps into conversation unprompted, per eligible message (default: `0.02`) |
| `JUMPIN_COOLDOWN_SECONDS` | Minimum seconds between jump-in attempts per channel (default: `300`) |

### Architecture
Chat generation, rolling history, and lore (mem0/Qdrant) all live in a separate service, [`boop-brain`](https://github.com/Chibbluffy/boop-brain), deployed on the AI server rather than in this repo — BoopBot only handles Discord I/O and a cheap local check for the jump-in feature. See that repo's README for setup/deployment.

## Database

The bot shares a PostgreSQL database with the boop.fish website. It reads and writes the `users` table, keyed by `discord_id`.

## Commands

#### Chatbot
- Mention the bot or reply to one of its messages to chat and get a response.
- The bot also occasionally jumps into conversation unprompted (tuned by `JUMPIN_PROBABILITY`/`JUMPIN_COOLDOWN_SECONDS`), similar to a real member chiming in — not on every message.
- Generation runs on a self-hosted Ollama instance via the `boop-brain` service (see Architecture above), with rolling per-channel chat history and long-term "lore" memory.
- Most messages get a fast reply from a small default model. If a message contains a link, an image attachment, or question/search-like phrasing ("what is...", "who is...", "look up...", etc.), `boop-brain` automatically escalates that reply to a larger model that can read the linked page, look at the image, or search the live web for an answer — no separate command needed, it's detected automatically.
- Use `!resetchat` to clear this channel's rolling chat history.

#### Lore
Long-term memory the bot draws on when chatting — some shared server-wide, some personal to you.

- Add shared guild lore
	```
	!lore add <text>
	```

- Add a personal fact about you
	```
	!lore addme <text>
	```

- List guild + your personal lore (paginated)
	```
	!lore list [page]
	```

- Delete a lore entry by its short id (shown in `!lore list`)
	```
	!lore forget <short_id>
	```

#### Fun
- Ask the magic 8-ball a yes/no question. The same question returns the same answer for 1 hour.
	```
	!8ball <question>
	```

- Roll a random number from 1 to N (default 100).
	```
	!roll [max]
	```

#### Events
- Create Event
	- Format
	```
	!create_event "Event Name" "Event Description" <discord_converted_time> <duration_in_minutes>
	```
	- Example
	```
	!create_event "GLEAGUE!!!!!" "" <t:1743987540:F> 30
	```
	- Will automatically ping users who have marked "Interested" 30 minutes and 5 minutes before the event begins.

#### Economy
- Check balance (yours or another user's)
	```
	!balance [@user]
	!bal [@user]
	```

- Collect 1,000 boops (once every 23 hours)
	```
	!daily
	```

- Beg for boops (only works when you have fewer than 100)
	```
	!beg
	```

- Give boops to another user
	```
	!give @user <amount>
	```

- View the top boop leaderboard
	```
	!richest
	!booplb
	```

- (Admin) Award boops to a user
	```
	!award @user <amount>
	```

#### Casino
Minimum bet: **10 boops**.

- Flip a coin
	```
	!betflip <amount> <h/t>
	!bf <amount> <h/t>
	!flip <amount> <h/t>
	```

- Bet roll (>66: 2×, >90: 3×, 100: 10×)
	```
	!betroll <amount>
	!br <amount>
	```

- Play blackjack (Hit / Stand / Double Down)
	```
	!blackjack <amount>
	!bj <amount>
	```

#### Fishing
- Cast your line and catch fish for boops
	```
	!fish
	```

- Browse the fishing shop (rods, floats, bait)
	```
	!shop
	```

- Buy a shop item
	```
	!buy <item> [quantity]
	```

- Equip a rod, float, or set active bait
	```
	!equip <item>
	```

- Unequip your float or active bait
	```
	!unequip <float|bait>
	```

- Set Fish Whisperer focus tier (0 = off, 1–5)
	```
	!fishfocus <0-5>
	```

- View your inventory
	```
	!inventory
	!inv
	```

- Browse the fish guide / catch reference
	```
	!fishguide
	!fishbook
	!fishdex
	```

- View drop rates / catch chances
	```
	!fishrates
	!fishchances
	!droprates
	```

- View personal best fishing records (yours or another user's)
	```
	!fishrecords [@user]
	!fishpb [@user]
	```

- View the best fishers leaderboard
	```
	!bestfishers
	```

#### Quotes
- List quotes (optionally filtered by keyword, paginated)
	```
	!quotelist [keyword]
	!ql [keyword]
	```

- Print a random quote by keyword
	```
	!quoteprint <keyword>
	!qp <keyword>
	!q <keyword>
	```

- Get a quote by ID
	```
	!quoteget <id>
	!qg <id>
	```

- Show a quote embed by ID
	```
	!quoteshow <id>
	!qshow <id>
	```

- Add a quote
	```
	!quoteadd <keyword> [text]
	!qa <keyword> [text]
	```

- Search for a quote by text within a keyword
	```
	!quotesearch <keyword> <search_term>
	!qsearch <keyword> <search_term>
	!qfind <keyword> <search_term>
	```

- Delete a quote by ID
	```
	!quotedelete <id>
	!qd <id>
	```

- Delete all quotes by a user
	```
	!quotedeleteauthor @user
	!qda @user
	```

- Delete all quotes (optionally for a keyword)
	```
	!quotesdeleteall [keyword]
	!qdall [keyword]
	```

- Export all quotes as a YAML file
	```
	!quotesexport
	!qexport
	```

- Import quotes from an attached YAML file
	```
	!quotesimport
	!qimport
	```

#### Gear
- Save/update gear image
	```
	!gear <image_url>
	```
	or attach an image:
	```
	!gear
	```

- View your gear image
	```
	!gear
	```

- View another user's gear image
	```
	!checkgear @user
	```
	or
	```
	!gear @user
	```

#### Gear Stats
- Set stats
	```
	!setap <number>
	!setaap <number>
	!setdp <number>
	```

- View your gear score
	```
	!showgs
	!gs
	```

- View guild gear scores (alphabetical)
	```
	!showguildgs
	```

- View gear score leaderboard, guild members only (paginated, sorted by GS)
	```
	!gslb
	```

- View AP leaderboard, guild members only (sorted by effective AP)
	```
	!aplb
	```

- View gear score leaderboard including non-members (paginated)
	```
	!gsall
	```

#### Moderation
Requires the **Manage Messages** permission.

- Delete messages
	```
	!prune                   — delete the command + the message before it
	!prune <count>           — delete last N messages
	!prune @user             — delete user's messages in the last 100
	!prune @user <count>     — delete last N messages from user
	!clr / !clear            — aliases for !prune
	```

#### Chest Timer Management
- Chest timers are tracked automatically. (Commands currently disabled.)
