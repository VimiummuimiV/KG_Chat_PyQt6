"""Telegram Bot Bridge for XMPP"""

import asyncio
import logging
import os
import platform
import threading
import queue
from pathlib import Path
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

from xmpp import XMPPClient
from commands import AccountCommands
from messages import MessageParser


logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)


class TelegramBridge:
    """Telegram-XMPP Bridge"""
    
    def __init__(self):
        self.token = self._get_token()
        self.xmpp = XMPPClient()
        self.commands = AccountCommands(self.xmpp.account_manager)
        self.msg_queue = queue.Queue()
        self.chat_ids = set()
        
        self.xmpp.set_message_callback(self.on_xmpp_message)
        self.xmpp.set_presence_callback(self.on_xmpp_presence)
        
        self.app = Application.builder().token(self.token).build()
        self._register_handlers()
    
    def _get_token_path(self) -> Path:
        """Get token file path"""
        system = platform.system()
        
        if system == "Windows":
            data_dir = Path.home() / "Desktop" / "xmpp_chat_data"
        elif system == "Darwin":
            data_dir = Path.home() / "Desktop" / "xmpp_chat_data"
        elif system == "Linux":
            if os.path.exists("/data/data/com.termux"):
                data_dir = Path.home() / "storage" / "shared" / "xmpp_chat_data"
            else:
                data_dir = Path.home() / "Desktop" / "xmpp_chat_data"
        else:
            data_dir = Path.home() / ".xmpp_chat_data"
        
        data_dir.mkdir(parents=True, exist_ok=True)
        return data_dir / "telegram_bot_token.txt"
    
    def _get_token(self) -> str:
        """Get or prompt for token"""
        token_path = self._get_token_path()
        
        if token_path.exists():
            try:
                with open(token_path, 'r') as f:
                    token = f.read().strip()
                    if token:
                        print(f"✅ Token loaded from: {token_path}")
                        return token
            except:
                pass
        
        print("\n" + "=" * 60)
        print("🤖 Telegram Bot Token Setup")
        print("=" * 60)
        print("Get token from @BotFather on Telegram")
        print(f"Will be saved to: {token_path}")
        print("=" * 60)
        
        token = input("\nEnter Telegram Bot Token: ").strip()
        
        if not token or ':' not in token:
            raise ValueError("Invalid token")
        
        with open(token_path, 'w') as f:
            f.write(token)
        
        if platform.system() != "Windows":
            os.chmod(token_path, 0o600)
        
        print(f"✅ Token saved to: {token_path}")
        return token
    
    def _register_handlers(self):
        """Register handlers"""
        self.app.add_handler(CommandHandler("start", self.start))
        self.app.add_handler(CommandHandler("help", self.help))
        self.app.add_handler(CommandHandler("accounts", self.accounts))
        self.app.add_handler(CommandHandler("add", self.add_account))
        self.app.add_handler(CommandHandler("remove", self.remove_account))
        self.app.add_handler(CommandHandler("switch", self.switch_account))
        self.app.add_handler(CommandHandler("active", self.active_account))
        self.app.add_handler(CommandHandler("connect", self.connect))
        self.app.add_handler(CommandHandler("disconnect", self.disconnect))
        self.app.add_handler(CommandHandler("status", self.status))
        self.app.add_handler(CommandHandler("users", self.users))
        self.app.add_handler(CommandHandler("online", self.online))
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.message))
    
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start command"""
        self.chat_ids.add(update.effective_chat.id)
        await update.message.reply_text(
            "🤖 *XMPP Chat Bot*\n\n"
            "Use /help for commands",
            parse_mode='Markdown'
        )
    
    async def help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Help command"""
        help_text = (
            "📋 *Commands:*\n\n"
            "*Accounts:*\n"
            "/accounts - List accounts\n"
            "/add <user\\_id> <login> <password> - Add account\n"
            "/remove <login> - Remove account\n"
            "/switch <login> - Switch account\n"
            "/active - Show active account\n\n"
            "*XMPP:*\n"
            "/connect - Connect to chat\n"
            "/disconnect - Disconnect\n"
            "/status - Connection status\n\n"
            "*Users:*\n"
            "/users - All users\n"
            "/online - Online users\n\n"
            "*Messages:*\n"
            "Type message to send to chat"
        )
        await update.message.reply_text(help_text, parse_mode='Markdown')
    
    async def accounts(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """List accounts"""
        result = self.commands.list_accounts()
        await update.message.reply_text(f"```\n{result}\n```", parse_mode='Markdown')
    
    async def add_account(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Add account"""
        if len(context.args) < 3:
            await update.message.reply_text(
                "Usage: `/add <user_id> <login> <password>`",
                parse_mode='Markdown'
            )
            return
        
        result = self.commands.add_account(context.args[0], context.args[1], context.args[2])
        await update.message.reply_text(result)
    
    async def remove_account(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Remove account"""
        if not context.args:
            await update.message.reply_text("Usage: `/remove <login>`", parse_mode='Markdown')
            return
        
        result = self.commands.remove_account(context.args[0])
        await update.message.reply_text(result)
    
    async def switch_account(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Switch account"""
        if not context.args:
            await update.message.reply_text("Usage: `/switch <login>`", parse_mode='Markdown')
            return
        
        result = self.commands.switch_account(context.args[0])
        await update.message.reply_text(result)
    
    async def active_account(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Active account"""
        result = self.commands.get_active()
        await update.message.reply_text(result)
    
    async def connect(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Connect to XMPP"""
        await update.message.reply_text("🔄 Connecting...")
        
        def connect_thread():
            try:
                if self.xmpp.connect():
                    rooms = self.xmpp.account_manager.get_rooms()
                    for room in rooms:
                        if room.get('auto_join'):
                            self.xmpp.join_room(room['jid'])
                    
                    self.msg_queue.put(("system", "✅ Connected!"))
                    
                    # Start listening in background
                    threading.Thread(target=self.xmpp.listen, daemon=True).start()
                else:
                    self.msg_queue.put(("system", "❌ Connection failed"))
            except Exception as e:
                self.msg_queue.put(("system", f"❌ Error: {e}"))
        
        threading.Thread(target=connect_thread, daemon=True).start()
    
    async def disconnect(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Disconnect"""
        self.xmpp.disconnect()
        self.xmpp.user_list.clear()
        await update.message.reply_text("🔌 Disconnected")
    
    async def status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Status"""
        is_connected = self.xmpp.sid is not None
        status = "🟢 Connected" if is_connected else "🔴 Disconnected"
        jid = self.xmpp.jid if is_connected else "N/A"
        user_count = len(self.xmpp.user_list.get_online())
        
        await update.message.reply_text(
            f"*Status:* {status}\n"
            f"*JID:* `{jid}`\n"
            f"*Users Online:* {user_count}",
            parse_mode='Markdown'
        )
    
    async def users(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """List all users"""
        result = self.xmpp.user_list.format_list(online_only=False)
        await update.message.reply_text(f"```\n{result}\n```", parse_mode='Markdown')
    
    async def online(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """List online users"""
        result = self.xmpp.user_list.format_list(online_only=True)
        await update.message.reply_text(f"```\n{result}\n```", parse_mode='Markdown')
    
    async def message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Send message to XMPP"""
        if not self.xmpp.sid:
            await update.message.reply_text("❌ Not connected. Use /connect first")
            return
        
        text = update.message.text
        if self.xmpp.send_message(text):
            await update.message.reply_text(f"📤 Sent: {text}")
        else:
            await update.message.reply_text("❌ Failed to send")
    
    def on_xmpp_message(self, message):
        """Handle XMPP message"""
        self.msg_queue.put(("message", message))
    
    def on_xmpp_presence(self, presence):
        """Handle XMPP presence"""
        self.msg_queue.put(("presence", presence))
    
    async def broadcast(self, text: str):
        """Broadcast to all chats"""
        for chat_id in self.chat_ids:
            try:
                await self.app.bot.send_message(chat_id=chat_id, text=text)
            except Exception as e:
                logger.error(f"Broadcast error: {e}")
    
    async def queue_processor(self):
        """Process message queue"""
        while True:
            try:
                if not self.msg_queue.empty():
                    msg_type, content = self.msg_queue.get_nowait()
                    
                    if msg_type == "message":
                        formatted = MessageParser.format_message(content)
                        await self.broadcast(formatted)
                    
                    elif msg_type == "presence":
                        formatted = MessageParser.format_presence(content)
                        await self.broadcast(formatted)
                    
                    elif msg_type == "system":
                        await self.broadcast(content)
                
                await asyncio.sleep(0.1)
            except Exception as e:
                logger.error(f"Queue error: {e}")
                await asyncio.sleep(1)
    
    async def post_init(self, application: Application):
        """Post init"""
        asyncio.create_task(self.queue_processor())
    
    def run(self):
        """Run bot"""
        logger.info("🤖 Starting Telegram bot...")
        self.app.post_init = self.post_init
        self.app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    print("=" * 60)
    print("🌉 Telegram-XMPP Bridge")
    print("=" * 60)
    print()
    
    bridge = TelegramBridge()
    bridge.run()
