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
- Uses Google Gemini models. Use `!resetchat` to cycle to the next model.

#### 8-Ball
- Ask the magic 8-ball a yes/no question.
- The same question returns the same answer for 1 hour to prevent re-rolling.
```
!8ball <question>
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

- View gear score leaderboard (paginated, sorted by GS)
	```
	!gslb
	```

#### Chest Timer Management
- Chest timers are tracked automatically. (Commands currently disabled.)
