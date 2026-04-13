import json
import logging
import os
from pathlib import Path

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)

from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

load_dotenv()

BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_CHAT_ID = int(os.environ.get("ADMIN_CHAT_ID", "0"))
WEBHOOK_URL = os.environ.get("WEBHOOK_URL")
PORT = int(os.environ.get("PORT", "8443"))
PARENTS_FILE = Path("parents.json")

# Conversation states
WAITING_CHILD_NAME = 0
WAITING_SEARCH_NAME = 1
WAITING_REMOVE_NAME = 2

# Pending registration requests: {request_id: {"parent_id": str, "child_name": str, "display": str}}
pending_requests: dict[str, dict[str, str]] = {}
_next_request_id = 0


def next_request_id() -> str:
    global _next_request_id
    _next_request_id += 1
    return str(_next_request_id)


def load_parents() -> dict[str, str]:
    if PARENTS_FILE.exists():
        return json.loads(PARENTS_FILE.read_text(encoding="utf-8"))
    return {}


def save_parents(parents: dict[str, str]) -> None:
    PARENTS_FILE.write_text(json.dumps(parents, indent=2, ensure_ascii=False), encoding="utf-8")


def is_admin(chat_id: int) -> bool:
    return chat_id == ADMIN_CHAT_ID


# --------------- Parent commands ---------------

async def cmd_register(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start registration — ask for child name."""
    await update.message.reply_text("What is your child's name?")
    return WAITING_CHILD_NAME


async def receive_child_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive child name and send approval request to admin."""
    child_name = update.message.text.strip()
    chat_id = str(update.effective_chat.id)
    user = update.effective_user
    display = user.full_name or user.username or chat_id

    req_id = next_request_id()
    pending_requests[req_id] = {"parent_id": chat_id, "child_name": child_name, "display": display}

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Approve", callback_data=f"approve:{req_id}"),
            InlineKeyboardButton("Deny", callback_data=f"deny:{req_id}"),
        ]
    ])

    await context.bot.send_message(
        chat_id=ADMIN_CHAT_ID,
        text=(
            f"New registration request:\n"
            f"Parent: {display} (ID: {chat_id})\n"
            f"Child: {child_name}"
        ),
        reply_markup=keyboard,
    )
    await update.message.reply_text(
        "Your registration request has been sent. You'll be notified once approved!"
    )
    return ConversationHandler.END


async def cancel_registration(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel registration conversation."""
    await update.message.reply_text("Registration cancelled.")
    return ConversationHandler.END


# --------------- Admin callback for approve/deny buttons ---------------

async def handle_approval(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle Approve / Deny button presses."""
    query = update.callback_query
    await query.answer()

    if not is_admin(query.from_user.id):
        return

    action, req_id = query.data.split(":", 1)
    req = pending_requests.pop(req_id, None)

    if not req:
        await query.edit_message_text("This request has already been handled.")
        return

    parent_id = req["parent_id"]
    child_name = req["child_name"]

    if action == "approve":
        parents = load_parents()
        parents[parent_id] = child_name
        save_parents(parents)

        await query.edit_message_text(f"Approved: {parent_id} — {child_name}")
        try:
            await context.bot.send_message(
                chat_id=int(parent_id),
                text=f"You have been registered for photos of {child_name}!",
            )
        except Exception:
            await context.bot.send_message(
                chat_id=ADMIN_CHAT_ID,
                text="(Could not notify the parent — they may need to start the bot first.)",
            )
    else:
        await query.edit_message_text(f"Denied: {parent_id} — {child_name}")
        try:
            await context.bot.send_message(
                chat_id=int(parent_id),
                text="Your registration request was not approved.",
            )
        except Exception:
            pass


async def cmd_myid(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show the user their Telegram chat ID."""
    await update.message.reply_text(f"Your chat ID is: {update.effective_chat.id}")


# --------------- Admin commands ---------------

async def cmd_addparent(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/addparent <chat_id> <child_name>"""
    if not is_admin(update.effective_chat.id):
        await update.message.reply_text("Unauthorized.")
        return

    if len(context.args) < 2:
        await update.message.reply_text("Usage: /addparent <chat_id> <child_name>")
        return

    parent_id = context.args[0]
    child_name = " ".join(context.args[1:])
    parents = load_parents()
    parents[parent_id] = child_name
    save_parents(parents)

    await update.message.reply_text(f"Added parent {parent_id} for child '{child_name}'.")
    try:
        await context.bot.send_message(
            chat_id=int(parent_id),
            text=f"You have been registered for photos of {child_name}!",
        )
    except Exception:
        await update.message.reply_text("(Could not notify the parent — they may need to start the bot first.)")


async def cmd_listparents(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/listparents — show all registered parents."""
    if not is_admin(update.effective_chat.id):
        await update.message.reply_text("Unauthorized.")
        return

    parents = load_parents()
    if not parents:
        await update.message.reply_text("No parents registered yet.")
        return

    lines = [f"  {pid} — {name}" for pid, name in parents.items()]
    await update.message.reply_text("Registered parents:\n" + "\n".join(lines))


async def cmd_removeparent(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """/removeparent — search by name then confirm."""
    if not is_admin(update.effective_chat.id):
        await update.message.reply_text("Unauthorized.")
        return ConversationHandler.END

    await update.message.reply_text("Type the child's name (or part of it) to search:")
    return WAITING_REMOVE_NAME


async def receive_remove_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Search parents by name and show remove buttons."""
    query = update.message.text.strip().lower()
    parents = load_parents()

    matches = {pid: name for pid, name in parents.items() if query in name.lower()}

    if not matches:
        await update.message.reply_text("No match found. Try again or /cancel:")
        return WAITING_REMOVE_NAME

    buttons = []
    for pid, name in list(matches.items())[:10]:
        req_id = next_request_id()
        pending_requests[req_id] = {"parent_id": pid, "child_name": name}
        buttons.append([InlineKeyboardButton(name, callback_data=f"remove:{req_id}")])

    if len(matches) > 10:
        await update.message.reply_text(
            f"Found {len(matches)} matches, showing first 10. Be more specific to narrow down.",
        )

    await update.message.reply_text(
        "Select a parent to remove:",
        reply_markup=InlineKeyboardMarkup(buttons),
    )
    return ConversationHandler.END


async def handle_remove(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the remove button press."""
    query = update.callback_query
    await query.answer()

    if not is_admin(query.from_user.id):
        return

    _, req_id = query.data.split(":", 1)
    req = pending_requests.pop(req_id, None)

    if not req:
        await query.edit_message_text("This selection has expired.")
        return

    parent_id = req["parent_id"]
    child_name = req["child_name"]

    parents = load_parents()
    if parent_id in parents:
        parents.pop(parent_id)
        save_parents(parents)
        await query.edit_message_text(f"Removed: {child_name}")
    else:
        await query.edit_message_text(f"{child_name} was already removed.")


async def cancel_remove(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel remove conversation."""
    await update.message.reply_text("Remove cancelled.")
    return ConversationHandler.END


async def cmd_sendphoto(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Admin: /sendphoto — start the send-photo conversation."""
    if not is_admin(update.effective_chat.id):
        await update.message.reply_text("Unauthorized.")
        return ConversationHandler.END

    replied = update.message.reply_to_message
    if not replied or not replied.photo:
        await update.message.reply_text("Please reply to a photo with /sendphoto.")
        return ConversationHandler.END

    # Store the photo info for later
    photo = replied.photo[-1]
    context.user_data["pending_photo"] = photo.file_id
    context.user_data["pending_caption"] = replied.caption or ""

    await update.message.reply_text("Type the child's name (or part of it) to search:")
    return WAITING_SEARCH_NAME


async def receive_search_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Search parents by child name and show buttons."""
    query = update.message.text.strip().lower()
    parents = load_parents()

    matches = {pid: name for pid, name in parents.items() if query in name.lower()}

    if not matches:
        await update.message.reply_text("No match found. Try again or /cancel:")
        return WAITING_SEARCH_NAME

    # Show up to 10 matches as buttons (paginated rows of 1)
    buttons = []
    for pid, name in list(matches.items())[:10]:
        req_id = next_request_id()
        pending_requests[req_id] = {
            "parent_id": pid,
            "child_name": name,
            "photo_id": context.user_data.get("pending_photo", ""),
            "caption": context.user_data.get("pending_caption", ""),
        }
        buttons.append([InlineKeyboardButton(name, callback_data=f"sendto:{req_id}")])

    if len(matches) > 10:
        await update.message.reply_text(
            f"Found {len(matches)} matches, showing first 10. Be more specific to narrow down.",
        )

    await update.message.reply_text(
        "Select a child to send the photo to:",
        reply_markup=InlineKeyboardMarkup(buttons),
    )
    return ConversationHandler.END


async def handle_sendto(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the sendto button press — actually send the photo."""
    query = update.callback_query
    await query.answer()

    if not is_admin(query.from_user.id):
        return

    _, req_id = query.data.split(":", 1)
    req = pending_requests.pop(req_id, None)

    if not req:
        await query.edit_message_text("This selection has expired.")
        return

    parent_id = req["parent_id"]
    child_name = req["child_name"]
    photo_id = req["photo_id"]
    caption = req["caption"]

    try:
        await context.bot.send_photo(
            chat_id=int(parent_id),
            photo=photo_id,
            caption=caption,
        )
        await query.edit_message_text(f"Photo sent to {child_name}!")
    except Exception as e:
        await query.edit_message_text(f"Failed to send to {child_name}: {e}")


async def cancel_sendphoto(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel sendphoto conversation."""
    context.user_data.pop("pending_photo", None)
    context.user_data.pop("pending_caption", None)
    await update.message.reply_text("Send photo cancelled.")
    return ConversationHandler.END


async def cmd_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin replies to a photo with /broadcast to send it to ALL registered parents."""
    if not is_admin(update.effective_chat.id):
        await update.message.reply_text("Unauthorized.")
        return

    replied = update.message.reply_to_message
    if not replied or not replied.photo:
        await update.message.reply_text("Please reply to a photo message with /broadcast.")
        return

    parents = load_parents()
    if not parents:
        await update.message.reply_text("No parents registered.")
        return

    photo = replied.photo[-1]
    caption = replied.caption or ""
    success, failed = 0, 0

    for parent_id in parents:
        try:
            await context.bot.send_photo(
                chat_id=int(parent_id),
                photo=photo.file_id,
                caption=caption,
            )
            success += 1
        except Exception:
            failed += 1

    await update.message.reply_text(f"Broadcast complete: {success} sent, {failed} failed.")


# --------------- Main ---------------

def main() -> None:
    if not BOT_TOKEN:
        print("ERROR: BOT_TOKEN not set.")
        return
    if not ADMIN_CHAT_ID:
        print("ERROR: ADMIN_CHAT_ID not set.")
        return
    if not WEBHOOK_URL:
        print("ERROR: WEBHOOK_URL not set.")
        return

    app = Application.builder().token(BOT_TOKEN).build()

    # Registration conversation: /register → asks for name → sends to admin
    register_conv = ConversationHandler(
        entry_points=[CommandHandler("register", cmd_register)],
        states={
            WAITING_CHILD_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_child_name)],
        },
        fallbacks=[CommandHandler("cancel", cancel_registration)],
        name="register_conv",
        per_message=False,
    )
    app.add_handler(register_conv)

    # Sendphoto conversation: /sendphoto (reply to photo) → search name → pick button
    sendphoto_conv = ConversationHandler(
        entry_points=[CommandHandler("sendphoto", cmd_sendphoto)],
        states={
            WAITING_SEARCH_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_search_name)],
        },
        fallbacks=[CommandHandler("cancel", cancel_sendphoto)],
        name="sendphoto_conv",
        per_message=False,
    )
    app.add_handler(sendphoto_conv)

    # Removeparent conversation: /removeparent → search name → pick button
    remove_conv = ConversationHandler(
        entry_points=[CommandHandler("removeparent", cmd_removeparent)],
        states={
            WAITING_REMOVE_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_remove_name)],
        },
        fallbacks=[CommandHandler("cancel", cancel_remove)],
        name="remove_conv",
        per_message=False,
    )
    app.add_handler(remove_conv)

    # Inline button callbacks
    app.add_handler(CallbackQueryHandler(handle_approval, pattern=r"^(approve|deny):"))
    app.add_handler(CallbackQueryHandler(handle_sendto, pattern=r"^sendto:"))
    app.add_handler(CallbackQueryHandler(handle_remove, pattern=r"^remove:"))

    # Parent commands
    app.add_handler(CommandHandler("myid", cmd_myid))

    # Admin commands
    app.add_handler(CommandHandler("addparent", cmd_addparent))
    app.add_handler(CommandHandler("listparents", cmd_listparents))
    app.add_handler(CommandHandler("broadcast", cmd_broadcast))

    # Catch-all for non-admin messages
    async def fallback_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not is_admin(update.effective_chat.id):
            await update.message.reply_text(
                "This bot is for receiving photos only.\n"
                "To contact us, please message us on WhatsApp:\n"
                "https://wa.me/96171147579"
            )

    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, fallback_message))

    print("Bot is running via webhook...")
    app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        webhook_url=f"{WEBHOOK_URL}/{BOT_TOKEN}",
        url_path=BOT_TOKEN,
    )


if __name__ == "__main__":
    import asyncio
    asyncio.set_event_loop(asyncio.new_event_loop())
    main()
