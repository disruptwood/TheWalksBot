import logging
import sqlite3
from datetime import datetime, time
import pytz
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from telegram.constants import ParseMode

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


def init_db():
    conn = sqlite3.connect('user_rooms.db')
    cursor = conn.cursor()
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS user_rooms (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        selected_room TEXT,
        last_selection_date TEXT
    )
    ''')
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS bot_state (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        last_reset_date TEXT
    )
    ''')
    # New table for storing forwarded message mapping
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS forwarded_messages (
        admin_msg_id INTEGER PRIMARY KEY,
        user_chat_id INTEGER,
        user_id INTEGER,
        timestamp TEXT
    )
    ''')
    # Initialize bot_state if it doesn't exist
    cursor.execute('INSERT OR IGNORE INTO bot_state (id, last_reset_date) VALUES (1, NULL)')
    conn.commit()
    conn.close()

# Initialize database
init_db()


def save_forwarded_message(admin_msg_id, user_chat_id, user_id):
    """Store forwarded message data in the database"""
    conn = sqlite3.connect('user_rooms.db')
    cursor = conn.cursor()
    timestamp = datetime.now().isoformat()
    cursor.execute('''
    INSERT OR REPLACE INTO forwarded_messages 
    (admin_msg_id, user_chat_id, user_id, timestamp) 
    VALUES (?, ?, ?, ?)
    ''', (admin_msg_id, user_chat_id, user_id, timestamp))
    conn.commit()
    conn.close()
    logger.info(f"Saved forwarded message mapping: admin_msg_id={admin_msg_id}, user_chat_id={user_chat_id}")


def get_forwarded_message(admin_msg_id):
    """Retrieve forwarded message data from the database"""
    conn = sqlite3.connect('user_rooms.db')
    cursor = conn.cursor()
    cursor.execute('''
    SELECT user_chat_id, user_id FROM forwarded_messages 
    WHERE admin_msg_id = ?
    ''', (admin_msg_id,))
    result = cursor.fetchone()
    conn.close()

    if result:
        return {
            'chat_id': result[0],
            'user_id': result[1]
        }
    return None


# Function to check if reset is needed
def check_and_reset_if_needed():
    conn = sqlite3.connect('user_rooms.db')
    cursor = conn.cursor()

    # Get the current date and time in Israel timezone
    israel_tz = pytz.timezone('Asia/Jerusalem')
    now = datetime.now(israel_tz)
    current_date = now.date().isoformat()

    # Check if it's past 9am
    is_past_9am = now.time() >= time(9, 0)

    # Get the last reset date
    cursor.execute('SELECT last_reset_date FROM bot_state WHERE id = 1')
    last_reset_date = cursor.fetchone()[0]

    # Check if reset is needed
    if is_past_9am and (not last_reset_date or last_reset_date != current_date):
        # Reset all user selections
        cursor.execute('UPDATE user_rooms SET last_selection_date = NULL')

        # Update last reset date
        cursor.execute('UPDATE bot_state SET last_reset_date = ?', (current_date,))

        conn.commit()
        logger.info(f"All room selections have been reset on {current_date}")

    conn.close()


# Function to check if user has made a selection today
def has_selected_today(user_id):
    conn = sqlite3.connect('user_rooms.db')
    cursor = conn.cursor()

    # Get the current date in Israel timezone
    israel_tz = pytz.timezone('Asia/Jerusalem')
    current_date = datetime.now(israel_tz).date().isoformat()

    cursor.execute('SELECT last_selection_date FROM user_rooms WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    conn.close()

    if result and result[0] == current_date:
        return True
    return False


# Function to get user's current room and username
def get_user_info(user_id):
    conn = sqlite3.connect('user_rooms.db')
    cursor = conn.cursor()

    cursor.execute('SELECT selected_room, username FROM user_rooms WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    conn.close()

    if result:
        return {"room": result[0], "username": result[1]}
    return None


# Function to get user's current room (for backward compatibility)
def get_user_room(user_id):
    user_info = get_user_info(user_id)
    if user_info:
        return user_info["room"]
    return None


def get_users_by_room(room=None):
    conn = sqlite3.connect('user_rooms.db')
    cursor = conn.cursor()

    if room:
        # Get users from a specific room
        cursor.execute('SELECT user_id FROM user_rooms WHERE selected_room = ?', (room,))
    else:
        # Get all users
        cursor.execute('SELECT user_id FROM user_rooms')

    user_ids = [row[0] for row in cursor.fetchall()]
    conn.close()

    return user_ids


# Function to update user's room selection
def update_user_room(user_id, room, username):
    conn = sqlite3.connect('user_rooms.db')
    cursor = conn.cursor()

    # Get the current date in Israel timezone
    israel_tz = pytz.timezone('Asia/Jerusalem')
    current_date = datetime.now(israel_tz).date().isoformat()

    cursor.execute('''
    INSERT OR REPLACE INTO user_rooms (user_id, username, selected_room, last_selection_date)
    VALUES (?, ?, ?, ?)
    ''', (user_id, username, room, current_date))

    conn.commit()
    conn.close()


# Create room selection keyboard
def get_room_keyboard():
    keyboard = [
        [
            InlineKeyboardButton("Room 1", callback_data="room1"),
            InlineKeyboardButton("Room 2", callback_data="room2")
        ],
        [
            InlineKeyboardButton("Room 3", callback_data="room3"),
            InlineKeyboardButton("Room 4", callback_data="room4")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


# Command handler for /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Check if reset is needed
    check_and_reset_if_needed()

    await send_room_menu(update, context)


# Function to send room selection menu
async def send_room_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    current_room = get_user_room(user_id)

    message = "Please select a room:"
    if current_room and has_selected_today(user_id):
        message = f"You've selected {current_room}. You can change your selection:"

    await update.effective_message.reply_text(
        message,
        reply_markup=get_room_keyboard()
    )


# Callback handler for room selection buttons
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Check if reset is needed
    check_and_reset_if_needed()

    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    username = query.from_user.username or f"user_{user_id}"
    selected_room = query.data

    update_user_room(user_id, selected_room, username)

    await query.edit_message_text(
        text=f"You've selected {selected_room}. You can change your selection anytime.",
        reply_markup=get_room_keyboard()
    )


# Message handler for all messages
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"Chat ID: {update.effective_chat.id}")
    # Check if reset is needed
    check_and_reset_if_needed()

    user_id = update.effective_user.id

    # Check if this is a reply to a forwarded message
    if update.message and update.message.reply_to_message:
        # Only allow admin replies
        if update.effective_chat.id == -4796230051:  # Admin chat ID
            # Handle admin reply
            await handle_admin_reply(update, context)
        return

    # Don't process admin group messages unless they're commands or replies
    if update.effective_chat.id == -4796230051:
        if update.message and update.message.text and update.message.text.startswith('/'):
            # Let command handlers process these
            return
        # Ignore all other messages in admin group
        return

    # Check if user has selected a room today
    if not has_selected_today(user_id):
        # If user hasn't selected a room today, send them the menu and don't forward the message
        await send_room_menu(update, context)
        await update.message.reply_text("Please select a room first before sending messages.")
        return

    # User has selected a room today, proceed with forwarding the message
    user_info = get_user_info(user_id)
    room = user_info.get("room", "Unknown Room")
    username = user_info.get("username", f"user_{user_id}")

    # Message header for the admin
    header = f"*Message from {username}* | *Room: {room}*\n\n"

    # Forward the message to admin
    ADMIN_CHAT_ID = -4796230051

    # Handle different types of messages
    if update.message.text:
        # Text message
        admin_msg = await context.bot.send_message(
            chat_id=ADMIN_CHAT_ID,
            text=f"{header}{update.message.text}",
            parse_mode=ParseMode.MARKDOWN
        )
        # Store mapping in database instead of context
        save_forwarded_message(admin_msg.message_id, update.effective_chat.id, user_id)

    elif update.message.sticker:
        # Sticker
        admin_msg = await context.bot.send_sticker(
            chat_id=ADMIN_CHAT_ID,
            sticker=update.message.sticker.file_id
        )
        # Send the header as a separate message
        text_msg = await context.bot.send_message(
            chat_id=ADMIN_CHAT_ID,
            text=header,
            parse_mode=ParseMode.MARKDOWN,
            reply_to_message_id=admin_msg.message_id
        )
        # Store mapping in database
        save_forwarded_message(admin_msg.message_id, update.effective_chat.id, user_id)

    elif update.message.voice:
        # Voice message
        admin_msg = await context.bot.send_voice(
            chat_id=ADMIN_CHAT_ID,
            voice=update.message.voice.file_id,
            caption=header,
            parse_mode=ParseMode.MARKDOWN
        )
        # Store mapping in database
        save_forwarded_message(admin_msg.message_id, update.effective_chat.id, user_id)

    elif update.message.document:
        # Document
        admin_msg = await context.bot.send_document(
            chat_id=ADMIN_CHAT_ID,
            document=update.message.document.file_id,
            caption=header,
            parse_mode=ParseMode.MARKDOWN
        )
        # Store mapping in database
        save_forwarded_message(admin_msg.message_id, update.effective_chat.id, user_id)

    elif update.message.photo:
        # Photo (send the largest available size)
        admin_msg = await context.bot.send_photo(
            chat_id=ADMIN_CHAT_ID,
            photo=update.message.photo[-1].file_id,
            caption=header,
            parse_mode=ParseMode.MARKDOWN
        )
        # Store mapping in database
        save_forwarded_message(admin_msg.message_id, update.effective_chat.id, user_id)

    elif update.message.video:
        # Video
        admin_msg = await context.bot.send_video(
            chat_id=ADMIN_CHAT_ID,
            video=update.message.video.file_id,
            caption=header,
            parse_mode=ParseMode.MARKDOWN
        )
        # Store mapping in database
        save_forwarded_message(admin_msg.message_id, update.effective_chat.id, user_id)

    elif update.message.animation:
        # Animation/GIF
        admin_msg = await context.bot.send_animation(
            chat_id=ADMIN_CHAT_ID,
            animation=update.message.animation.file_id,
            caption=header,
            parse_mode=ParseMode.MARKDOWN
        )
        # Store mapping in database
        save_forwarded_message(admin_msg.message_id, update.effective_chat.id, user_id)

    elif update.message.video_note:
        logger.info("Received video_note")
        admin_msg = await context.bot.send_video_note(
            chat_id=ADMIN_CHAT_ID,
            video_note=update.message.video_note.file_id
        )
        # Send the header as a separate message since video_note can't have captions
        text_msg = await context.bot.send_message(
            chat_id=ADMIN_CHAT_ID,
            text=header,
            parse_mode=ParseMode.MARKDOWN,
            reply_to_message_id=admin_msg.message_id
        )
        # Store mapping in database
        save_forwarded_message(admin_msg.message_id, update.effective_chat.id, user_id)

    else:
        # Other types of messages
        admin_msg = await context.bot.send_message(
            chat_id=ADMIN_CHAT_ID,
            text=f"{header}[Unsupported message type]",
            parse_mode=ParseMode.MARKDOWN
        )
        # Store mapping in database
        save_forwarded_message(admin_msg.message_id, update.effective_chat.id, user_id)

    # Acknowledge receipt to user
    await update.message.reply_text("Message sent ✓")

# Function to get admin room selection keyboard
def get_admin_room_keyboard():
    keyboard = [
        [
            InlineKeyboardButton("Room 1", callback_data="admin_select_room1"),
            InlineKeyboardButton("Room 2", callback_data="admin_select_room2")
        ],
        [
            InlineKeyboardButton("Room 3", callback_data="admin_select_room3"),
            InlineKeyboardButton("Room 4", callback_data="admin_select_room4")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

# Function to handle admin replies
async def handle_admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Only process messages from the admin chat
    if update.effective_chat.id != -4796230051:  # Using the same admin chat ID from your code
        return
    # If it's not a command and we're not expecting a broadcast message, return immediately
    if not update.message.text.startswith('/') and 'pending_broadcast' not in context.bot_data:
        return
    message_text = update.message.text

    # Initialize pending_broadcast if it doesn't exist
    if 'pending_broadcast' not in context.bot_data:
        context.bot_data['pending_broadcast'] = {}

    # Handle the /send_all command
    if message_text == '/send_all':
        context.bot_data['pending_broadcast'] = {
            'type': 'all',
            'room': None,
            'message': None,
            'awaiting_message': True
        }
        await update.message.reply_text(
            "Please send the message you want to broadcast to all users."
        )
        return

    # Handle the /send_room command - now showing a room selection keyboard
    if message_text == '/send_room':
        await update.message.reply_text(
            "Select the room to send the message to:",
            reply_markup=get_admin_room_keyboard()
        )
        return

    # Handle the /confirm command
    if message_text == '/confirm':
        pending = context.bot_data.get('pending_broadcast', {})

        if not pending or not pending.get('message'):
            await update.message.reply_text(
                "Nothing to confirm. Please use /send_all or /send_room first."
            )
            return

        # Get the users to send to
        if pending['type'] == 'all':
            user_ids = get_users_by_room()
            target_desc = "all users"
        else:
            user_ids = get_users_by_room(pending['room'])
            target_desc = f"users in {pending['room']}"

        # Check if we have users to send to
        if not user_ids:
            await update.message.reply_text(
                f"No {target_desc} found to send message to."
            )
            context.bot_data['pending_broadcast'] = {}
            return

        # Send the message to each user
        message_data = pending['message']
        message_type = message_data['type']
        success_count = 0

        for user_id in user_ids:
            try:
                if message_type == 'text':
                    await context.bot.send_message(
                        chat_id=user_id,
                        text=message_data['content'],
                        parse_mode=ParseMode.MARKDOWN
                    )
                elif message_type == 'photo':
                    await context.bot.send_photo(
                        chat_id=user_id,
                        photo=message_data['file_id'],
                        caption=message_data.get('caption')
                    )
                elif message_type == 'video':
                    await context.bot.send_video(
                        chat_id=user_id,
                        video=message_data['file_id'],
                        caption=message_data.get('caption')
                    )
                elif message_type == 'document':
                    await context.bot.send_document(
                        chat_id=user_id,
                        document=message_data['file_id'],
                        caption=message_data.get('caption')
                    )
                elif message_type == 'voice':
                    await context.bot.send_voice(
                        chat_id=user_id,
                        voice=message_data['file_id'],
                        caption=message_data.get('caption')
                    )
                elif message_type == 'sticker':
                    await context.bot.send_sticker(
                        chat_id=user_id,
                        sticker=message_data['file_id']
                    )
                elif message_type == 'animation':
                    await context.bot.send_animation(
                        chat_id=user_id,
                        animation=message_data['file_id'],
                        caption=message_data.get('caption')
                    )
                elif message_type == 'video_note':
                    await context.bot.send_video_note(
                        chat_id=user_id,
                        video_note=message_data['file_id']
                    )
                success_count += 1
            except Exception as e:
                logger.error(f"Error sending message to user {user_id}: {e}")

        # Clear the pending broadcast
        context.bot_data['pending_broadcast'] = {}

        await update.message.reply_text(
            f"Message sent to {success_count} out of {len(user_ids)} {target_desc}."
        )
        return

    # Handle the /cancel command
    if message_text == '/cancel':
        if context.bot_data.get('pending_broadcast'):
            context.bot_data['pending_broadcast'] = {}
            await update.message.reply_text("Broadcast cancelled.")
        else:
            await update.message.reply_text("No pending broadcast to cancel.")
        return

    # Handle message for pending broadcast
    pending = context.bot_data.get('pending_broadcast', {})
    if pending and pending.get('awaiting_message'):
        message = update.message

        # Store the message based on its type
        if message.text and not message.text.startswith('/'):
            pending['message'] = {
                'type': 'text',
                'content': message.text
            }
        elif message.photo:
            pending['message'] = {
                'type': 'photo',
                'file_id': message.photo[-1].file_id,
                'caption': message.caption
            }
        elif message.video:
            pending['message'] = {
                'type': 'video',
                'file_id': message.video.file_id,
                'caption': message.caption
            }
        elif message.document:
            pending['message'] = {
                'type': 'document',
                'file_id': message.document.file_id,
                'caption': message.caption
            }
        elif message.voice:
            pending['message'] = {
                'type': 'voice',
                'file_id': message.voice.file_id,
                'caption': message.caption
            }
        elif message.sticker:
            pending['message'] = {
                'type': 'sticker',
                'file_id': message.sticker.file_id
            }
        elif message.animation:
            pending['message'] = {
                'type': 'animation',
                'file_id': message.animation.file_id,
                'caption': message.caption
            }
        elif message.video_note:
            pending['message'] = {
                'type': 'video_note',
                'file_id': message.video_note.file_id
            }
        else:
            await update.message.reply_text(
                "This message type is not supported for broadcasting. Please send text, photo, video, document, voice, sticker, animation, or video note."
            )
            return

        pending['awaiting_message'] = False
        context.bot_data['pending_broadcast'] = pending

        # Ask for confirmation
        if pending['type'] == 'all':
            target_desc = "all users"
        else:
            target_desc = f"users in {pending['room']}"

        await update.message.reply_text(
            f"You're about to send this message to {target_desc}.\n"
            f"Please reply with /confirm to send or /cancel to abort."
        )


# Callback handler for admin room selection
async def admin_room_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not query.data.startswith('admin_select_'):
        return

    room = query.data.replace('admin_select_', '')

    # Initialize the pending broadcast
    context.bot_data['pending_broadcast'] = {
        'type': 'room',
        'room': room,
        'message': None,
        'awaiting_message': True
    }

    await query.edit_message_text(
        f"You've selected {room}. Please send the message you want to broadcast to users in this room."
    )


async def handle_admin_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    admin_id = -4796230051

    # Log the chat ID and check if it matches the admin chat ID
    logger.info(f"Reply from chat ID: {update.effective_chat.id}, admin ID: {admin_id}")

    # Only process replies from the admin chat
    if update.effective_chat.id != admin_id:
        logger.info("Message not from admin chat, ignoring")
        return

    # Check if the message is a reply to a forwarded message
    if not update.message.reply_to_message:
        logger.info("Message is not a reply, ignoring")
        return

    # Get the original message ID that this is a reply to
    replied_to_id = update.message.reply_to_message.message_id

    # Get original sender info from database
    original_sender = get_forwarded_message(replied_to_id)
    if not original_sender:
        logger.error(f"Cannot find original message for reply to ID: {replied_to_id}")
        await update.message.reply_text("Cannot find the original message this is a reply to.")
        return

    original_chat_id = original_sender['chat_id']
    logger.info(f"Sending reply to user chat ID: {original_chat_id}")

    try:
        # Forward the admin's reply back to the user
        if update.message.text:
            await context.bot.send_message(
                chat_id=original_chat_id,
                text=f"*Reply from admin:*\n\n{update.message.text}",
                parse_mode=ParseMode.MARKDOWN
            )
        elif update.message.sticker:
            await context.bot.send_sticker(
                chat_id=original_chat_id,
                sticker=update.message.sticker.file_id
            )
        elif update.message.voice:
            await context.bot.send_voice(
                chat_id=original_chat_id,
                voice=update.message.voice.file_id,
                caption="Voice message from admin"
            )
        elif update.message.document:
            await context.bot.send_document(
                chat_id=original_chat_id,
                document=update.message.document.file_id,
                caption="Document from admin"
            )
        elif update.message.photo:
            await context.bot.send_photo(
                chat_id=original_chat_id,
                photo=update.message.photo[-1].file_id,
                caption="Photo from admin" if update.message.caption is None else update.message.caption
            )
        elif update.message.video:
            await context.bot.send_video(
                chat_id=original_chat_id,
                video=update.message.video.file_id,
                caption="Video from admin" if update.message.caption is None else update.message.caption
            )
        elif update.message.animation:
            await context.bot.send_animation(
                chat_id=original_chat_id,
                animation=update.message.animation.file_id,
                caption="GIF from admin" if update.message.caption is None else update.message.caption
            )
        elif update.message.video_note:
            await context.bot.send_video_note(
                chat_id=original_chat_id,
                video_note=update.message.video_note.file_id
            )
        else:
            await context.bot.send_message(
                chat_id=original_chat_id,
                text="Admin sent a message of unsupported type"
            )

        # Acknowledge to admin
        await update.message.reply_text("Reply sent to user ✓")

    except Exception as e:
        logger.error(f"Error sending reply to user: {e}")
        await update.message.reply_text(f"Error sending reply: {e}")

# Main function to run the bot
# Replace the main function with this fixed version
def main():
    # Create and run the bot
    app = ApplicationBuilder().token("BotToken").build()

    # Add handlers
    app.add_handler(CommandHandler("start", start))

    # Add admin room selection callback handler
    app.add_handler(CallbackQueryHandler(admin_room_callback, pattern="^admin_select_"))

    # Add user room selection callback handler
    app.add_handler(CallbackQueryHandler(button_callback))

    # Handle admin commands explicitly
    app.add_handler(CommandHandler(
        ["send_all", "send_room", "confirm", "cancel"],
        handle_admin_command,
        filters.Chat(chat_id=-4796230051)
    ))

    # Handle admin replies
    app.add_handler(MessageHandler(
        filters.Chat(chat_id=-4796230051) & filters.REPLY,
        handle_admin_reply
    ), group=1)

    # Handle pending broadcast messages - ONLY when we're expecting them
    app.add_handler(MessageHandler(
        filters.Chat(chat_id=-4796230051) & ~filters.COMMAND & ~filters.REPLY,
        handle_admin_command
    ), group=2)

    # Regular user message handler
    app.add_handler(MessageHandler(
        ~filters.Chat(chat_id=-4796230051) & ~filters.COMMAND,
        handle_message
    ), group=3)

    # Start the bot
    app.run_polling()


if __name__ == '__main__':
    main()
