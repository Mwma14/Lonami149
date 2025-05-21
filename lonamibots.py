import os
import logging
from datetime import datetime
from telethon.sync import TelegramClient
from telegram import Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    ContextTypes, ConversationHandler, filters
)

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Configuration - Replace these with your actual credentials
API_ID = 123456                      # Your Telegram API ID
API_HASH = 'your_api_hash'           # Your Telegram API Hash
BOT_TOKEN = 'your_bot_token'         # Your Bot Token from @BotFather
ADMIN_IDS = [12345678, 87654321]     # List of admin user IDs who can access all commands
SESSION_DIR = "business_sessions"    # Directory to store session files
LOG_FILE = "session_requests.log"    # File to log session requests

# Conversation states
PHONE, CODE = range(2)

class SessionManager:
    def __init__(self):
        os.makedirs(SESSION_DIR, exist_ok=True)
        self.user_sessions = {}

    def log_request(self, user_id, phone, status):
        with open(LOG_FILE, 'a') as f:
            f.write(f"{datetime.now()},{user_id},{phone},{status}\n")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start the session creation process."""
    user_id = update.effective_user.id
    
    # Check if user is admin or has access
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("⚠️ You are not authorized to use this service.")
        return ConversationHandler.END
        
    await update.message.reply_text(
        "📱 *Telegram Session Generator*\n\n"
        "To create a session file, please send your phone number in international format (e.g., +1234567890):\n\n"
        "Type /cancel to abort the process.",
        parse_mode='Markdown'
    )
    return PHONE

async def get_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the phone number input."""
    phone = update.message.text.strip()
    user_id = update.effective_user.id
    
    # Validate phone number format
    if not phone.startswith('+') or not phone[1:].isdigit():
        await update.message.reply_text("❌ Invalid phone format. Please use international format (e.g., +1234567890)")
        return PHONE
    
    # Store user data
    context.user_data['phone'] = phone
    context.user_data['start_time'] = datetime.now()
    
    await update.message.reply_text(f"🔐 Sending verification code to {phone}...")
    
    try:
        # Create client and send code
        session_path = os.path.join(SESSION_DIR, f"business_{phone[1:]}")
        client = TelegramClient(session_path, API_ID, API_HASH)
        await client.connect()
        sent_code = await client.send_code_request(phone)
        
        # Store client in user data (temporarily)
        context.user_data['client'] = client
        context.user_data['phone_code_hash'] = sent_code.phone_code_hash
        
        await update.message.reply_text(
            "📨 A verification code has been sent to your phone.\n\n"
            "Please enter the code you received (format: 1 2 3 4 5):\n\n"
            "Type /cancel to abort the process."
        )
        return CODE
    except Exception as e:
        logger.error(f"Error sending code to {phone}: {e}")
        await update.message.reply_text(f"❌ Error sending code: {str(e)}")
        return ConversationHandler.END

async def get_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the verification code input."""
    user_id = update.effective_user.id
    code = update.message.text.strip().replace(' ', '')
    phone = context.user_data.get('phone')
    client = context.user_data.get('client')
    phone_code_hash = context.user_data.get('phone_code_hash')
    
    if not all([phone, client, phone_code_hash]):
        await update.message.reply_text("❌ Session expired. Please start over with /create_session")
        return ConversationHandler.END
    
    try:
        # Verify the code
        await client.sign_in(phone, code, phone_code_hash=phone_code_hash)
        
        # Get session file path
        session_path = f"{client.session.filename}.session"
        
        # Check if session file exists
        if os.path.exists(session_path):
            # Send session file to user
            with open(session_path, 'rb') as f:
                await update.message.reply_document(
                    document=f,
                    filename=f"business_{phone[1:]}.session",
                    caption=f"✅ Success! Your session file for {phone} is attached.\n\n"
                           "⚠️ Keep this file secure as it provides access to your account!"
                )
            
            # Log successful creation
            manager = SessionManager()
            manager.log_request(user_id, phone, "SUCCESS")
            
            logger.info(f"Session created for {phone} by user {user_id}")
        else:
            await update.message.reply_text("❌ Session file not found. Please try again.")
    except Exception as e:
        logger.error(f"Login failed for {phone}: {e}")
        await update.message.reply_text(f"❌ Login failed: {str(e)}")
    finally:
        if client:
            await client.disconnect()
        
        # Clean up user data
        context.user_data.clear()
    
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel the current operation."""
    user_id = update.effective_user.id
    phone = context.user_data.get('phone')
    
    # Clean up any existing client connection
    client = context.user_data.get('client')
    if client:
        await client.disconnect()
    
    # Log cancellation
    if phone:
        manager = SessionManager()
        manager.log_request(user_id, phone, "CANCELLED")
    
    context.user_data.clear()
    await update.message.reply_text("❌ Operation cancelled.")
    return ConversationHandler.END

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command to get bot statistics."""
    user_id = update.effective_user.id
    
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("⚠️ You are not authorized to view statistics.")
        return
    
    try:
        # Count session files
        session_count = len([f for f in os.listdir(SESSION_DIR) if f.endswith('.session')])
        
        # Count log entries
        try:
            with open(LOG_FILE, 'r') as f:
                log_count = len(f.readlines())
        except FileNotFoundError:
            log_count = 0
        
        await update.message.reply_text(
            f"📊 *Bot Statistics*\n\n"
            f"• Active sessions: {session_count}\n"
            f"• Total requests logged: {log_count}\n\n"
            f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Error getting stats: {e}")
        await update.message.reply_text("❌ Error retrieving statistics.")

def main():
    """Start the bot."""
    # Initialize session manager
    manager = SessionManager()
    
    # Create application
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    
    # Add conversation handler for session creation
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('create_session', start)],
        states={
            PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_phone)],
            CODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_code)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )
    
    # Add command handlers
    app.add_handler(conv_handler)
    app.add_handler(CommandHandler('stats', stats))
    
    # Start the bot
    logger.info("Starting bot...")
    app.run_polling()

if __name__ == '__main__':
    main()