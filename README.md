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
| `GOOGLE_API_KEY` | Google Gemini API key |
| `DATABASE_URL` | PostgreSQL connection string (e.g. `postgres://boop:password@localhost:5432/boopfish`) |
| `CHATBOT_CONTEXT_FILE` | Path to the chatbot context file (default: `chatbot_context.txt`) |

### `chatbot_context.txt`
Contains the system prompt / personality instructions sent to the Gemini model at startup. Edit this file to change the bot's behavior, add/remove guild members, or update context — no code changes needed. The bot must be restarted for changes to take effect.

## Database

The bot shares a PostgreSQL database with the boop.fish website. It reads and writes the `users` table, keyed by `discord_id`.

## Commands

#### Chatbot
- Mention the bot or reply to one of its messages to chat and get a response.
- Personality and context are configured in `chatbot_context.txt`.
- Uses Google Gemini (`gemini-2.5-flash-lite` / `gemini-2.5-flash`). Use `!resetchat` to cycle to the next model.

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
