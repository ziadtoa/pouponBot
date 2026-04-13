# Poupon City - Daycare Photo Bot

A Telegram bot that allows daycare staff to send photos to parents. Parents register through the bot and an admin approves them. Once approved, staff can send individual or broadcast photos to all registered parents.

## Features

- **Parent self-registration** with admin approval workflow
- **Send photos to individual parents** with name search
- **Broadcast photos** to all registered parents at once
- **Remove parents** with interactive name search
- **Persistent storage** of parent data in JSON

## Commands

### Parent Commands

| Command | Description |
|---------|-------------|
| `/register` | Start registration. The bot asks for the child's name, then sends an approval request to the admin. |
| `/myid` | Show your Telegram chat ID. |
| `/cancel` | Cancel any active conversation. |

### Admin Commands

| Command | Description |
|---------|-------------|
| `/addparent <chat_id> <child_name>` | Manually add a parent (bypasses approval flow). |
| `/listparents` | List all registered parents and their children. |
| `/removeparent` | Search for a parent by child name and remove them via button selection. |
| `/sendphoto` | Reply to a photo, then search by child name to send it to a specific parent. |
| `/broadcast` | Reply to a photo to send it to all registered parents. |

## How It Works

### Registration Flow

1. Parent sends `/register` to the bot
2. Bot asks for the child's name
3. Parent types the child's name
4. Admin receives a notification with **Approve** / **Deny** buttons
5. Admin taps a button; parent gets notified of the result

### Sending Photos

1. Admin sends a photo to the bot (or forwards one)
2. Admin replies to that photo with `/sendphoto`
3. Bot asks for the child's name (partial match supported)
4. Matching parents appear as buttons
5. Admin taps the correct parent; photo is delivered

### Broadcasting Photos

1. Admin sends or forwards a photo to the bot
2. Admin replies to it with `/broadcast`
3. Photo is sent to every registered parent

## Setup

### Prerequisites

- Python 3.10+
- A Telegram bot token from [BotFather](https://t.me/BotFather)
- Your admin Telegram chat ID (send `/myid` to the bot to find it)

### Installation

```bash
git clone https://github.com/ziadtoa/pouponBot.git
cd pouponBot
pip install -r requirements.txt
```

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `BOT_TOKEN` | Yes | Telegram bot token from BotFather |
| `ADMIN_CHAT_ID` | Yes | Telegram chat ID of the admin user |
| `WEBHOOK_URL` | Yes | Public URL of your deployment (e.g. `https://your-app.onrender.com`) |
| `PORT` | No | Server port (default: `8443`, Render sets this automatically) |

For local development, create a `.env` file:

```
BOT_TOKEN=your_bot_token_here
ADMIN_CHAT_ID=your_chat_id_here
WEBHOOK_URL=https://your-app.onrender.com
```

### Deploy to Render

1. Push this repo to GitHub
2. Create a new **Web Service** on [Render](https://render.com)
3. Connect your GitHub repo
4. Set the environment variables above in the Render dashboard
5. Render will use the `Procfile` to start the bot automatically

### Setting Bot Commands in Telegram

Open [BotFather](https://t.me/BotFather), send `/setcommands`, select your bot, and paste:

```
register - Register for photos
myid - Show your chat ID
addparent - (Admin) Add a parent manually
listparents - (Admin) List all parents
removeparent - (Admin) Remove a parent
sendphoto - (Admin) Send photo to a parent
broadcast - (Admin) Send photo to all parents
```

## Data Storage

Parent data is stored in `parents.json` in the project root. Format:

```json
{
  "123456789": "Child Name",
  "987654321": "Another Child"
}
```

Keys are Telegram chat IDs, values are child names.

## Tech Stack

- [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot) v21.6
- Python 3.10+
- Webhook mode for production deployment
