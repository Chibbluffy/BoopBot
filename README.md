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
ExecStart=/usr/bin/python3 /home/ubuntu/BoopBot/bot.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```
3. Enable and start it:
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

## Commands

#### Chatbot
- Mention the bot or reply to one of its messages to chat and get a response
- The initial context is in a variable named `context` in `bot.py` if you need to change anything. 
- It is currently using google gemini models, and 

#### Events
- Create Event
	- Format
	```
	!create_event #voice_channel_name "Event Name" "Event Description" <discord_converted_time> <duration_in_minutes>
	```
	- Example
	```
	!create_event #General "GLEAGUE!!!!!" "" <t:1743987540:F> 30
	```
	- Will automatically ping users who have marked "Interested" 30 minute and 5 minutes before the event begins

#### Gear
- Update Gear
	- Format
	```
	!gear <image_url>
	```
	or
	```
	!gear <attached image>
	```

- View Gear
	- Format
	```
	!gear
	```

#### Gear stats
- Set AP
	- Format
	```
	!setap <number>
	```

- Set Awakened AP
	- Format
	```
	!setaap <number>
	```

- Set DP
	- Format
	```
	!setdp <number>
	```

- Show GS
	- Format
	```
	!showgs
	```
- Show leaderboard
	- Format
	```
	!showgsleaderboard
	```

#### Chest Timer Management
- 