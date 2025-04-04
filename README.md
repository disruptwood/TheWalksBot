# Telegram Bot with Room Selection and Admin Forwarding

This bot lets users choose a room each day and send messages to an admin chat. The admin can reply or broadcast messages back to users.

## Features
- Users pick one of four rooms, once a day, resetting automatically at 9 AM Israel time.
- Messages from users are automatically forwarded to the admin chat.
- Admin can reply to forwarded messages or broadcast announcements to all or specific rooms.

## Getting Started
1. Install dependencies with `pip install -r requirements.txt`.
2. Edit the `main()` function to set:
   - `app = ApplicationBuilder().token("YOUR_BOT_TOKEN").build()`  
   - The `ADMIN_CHAT_ID` (-4796230051 in the code).
3. Run the bot: `python bot.py`.

## Commands
- **/start** – Users select or change their room.
- **/send_all** – Admin prepares a broadcast to all users.
- **/send_room** – Admin prepares a broadcast to a chosen room.
- **/confirm** – Sends the pending broadcast.
- **/cancel** – Cancels the pending broadcast.

## How It Works
1. On **/start**, users choose a room from a keyboard.
2. User messages are forwarded to the admin group with “Room” and username info.
3. Replies from the admin group are relayed back to the user.
4. Auto-reset ensures each user can choose only one room daily.
