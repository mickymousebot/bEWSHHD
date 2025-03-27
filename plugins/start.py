#(©)MrGhostsx

import os
import asyncio
import logging
from pyrogram import Client, filters, __version__
from pyrogram.enums import ParseMode
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.errors import FloodWait, UserIsBlocked, InputUserDeactivated, MessageNotModified

from bot import Bot
from config import ADMINS, FORCE_MSG, START_MSG, CUSTOM_CAPTION, DISABLE_CHANNEL_BUTTON, PROTECT_CONTENT, VERIFY, VERIFY_TUTORIAL, BOT_USERNAME
from helper_func import subscribed, encode, decode, get_messages
from database.database import add_user, del_user, full_userbase, present_user
from utils import verify_user, check_token, check_verification, get_token

logger = logging.getLogger(__name__)

async def safe_edit_message(message, text, **kwargs):
    """Safely edit message handling MessageNotModified errors"""
    try:
        if (message.text != text or 
            message.reply_markup != kwargs.get('reply_markup') or
            message.disable_web_page_preview != kwargs.get('disable_web_page_preview', True)):
            await message.edit_text(
                text=text,
                disable_web_page_preview=kwargs.get('disable_web_page_preview', True),
                reply_markup=kwargs.get('reply_markup')
            )
    except MessageNotModified:
        logger.debug("Message not modified - skipping edit")
    except Exception as e:
        logger.error(f"Failed to edit message: {e}", exc_info=True)
        raise

@Bot.on_message(filters.command('start') & filters.private & subscribed)
async def start_command(client: Client, message: Message):
    try:
        # Verification check for all users
        if VERIFY and not await check_verification(client, message.from_user.id):
            btn = [
                [InlineKeyboardButton("🔐 Verify Now", url=await get_token(client, message.from_user.id, f"https://telegram.me/{BOT_USERNAME}?start="))],
                [InlineKeyboardButton("❓ How To Verify", url=VERIFY_TUTORIAL)]
            ]
            return await message.reply_text(
                text="<b>🔒 VERIFICATION REQUIRED</b>\n\nYou must verify before accessing any files!\n\n<i>Click the button below to verify:</i>",
                protect_content=True,
                reply_markup=InlineKeyboardMarkup(btn)
            )

        # Handle verification callback
        if len(message.command) > 1:
            data = message.command[1]
            if data.startswith("verify-"):
                parts = data.split("-")
                if len(parts) == 3:
                    userid = parts[1]
                    token = parts[2]
                    
                    # Verify user matches the link
                    if not userid.isdigit() or str(message.from_user.id) != userid:
                        return await message.reply_text(
                            text="<b>⚠️ This verification link isn't yours!</b>",
                            protect_content=True
                        )
                    
                    # Check token validity
                    is_valid = await check_token(client, userid, token)
                    if is_valid:
                        await verify_user(client, userid, token)
                        await message.reply_text(
                            text=f"""<b>✅ VERIFICATION SUCCESSFUL!</b>

👋 Hello {message.from_user.mention},
You now have full access to all files.

⏳ Access valid until midnight (UTC)""",
                            protect_content=True,
                            reply_markup=InlineKeyboardMarkup([
                                [InlineKeyboardButton("📂 Access Files", callback_data="start")]
                            ])
                        )
                    else:
                        await message.reply_text(
                            text="<b>⌛ Verification link expired!\n\nPlease generate a new verification link.</b>",
                            protect_content=True,
                            reply_markup=InlineKeyboardMarkup([
                                [InlineKeyboardButton("🔄 Get New Link", callback_data="get_verify")]
                            ])
                        )
                    return

        # Add user to database if not present
        user_id = message.from_user.id
        if not await present_user(user_id):
            try:
                await add_user(user_id)
            except Exception as e:
                logger.error(f"Error adding user {user_id}: {e}")

        # File access handling (only reaches here if verified or VERIFY is False)
        if len(message.command) > 1 and not message.command[1].startswith("verify-"):
            # Final verification check before file access
            if VERIFY and not await check_verification(client, user_id):
                btn = [
                    [InlineKeyboardButton("🔐 Verify Now", url=await get_token(client, user_id, f"https://telegram.me/{BOT_USERNAME}?start="))],
                    [InlineKeyboardButton("❓ How To Verify", url=VERIFY_TUTORIAL)]
                ]
                return await message.reply_text(
                    text="<b>🔒 VERIFICATION REQUIRED</b>\n\nYou must verify before accessing any files!",
                    protect_content=True,
                    reply_markup=InlineKeyboardMarkup(btn)
            
            # File request processing
            try:
                base64_string = message.command[1]
                string = await decode(base64_string)
                argument = string.split("-")
                
                if len(argument) in [2, 3]:
                    try:
                        if len(argument) == 3:
                            start = int(int(argument[1]) / abs(client.db_channel.id))
                            end = int(int(argument[2]) / abs(client.db_channel.id))
                            ids = range(start, end+1) if start <= end else []
                        else:
                            ids = [int(int(argument[1]) / abs(client.db_channel.id))]
                    except (ValueError, IndexError):
                        return

                    temp_msg = await message.reply("<b>⏳ Processing your request...</b>")
                    try:
                        messages = await get_messages(client, ids)
                    except Exception as e:
                        logger.error(f"Error getting messages: {e}")
                        await message.reply_text("<b>❌ Error: Could not retrieve files</b>")
                        return
                    finally:
                        await temp_msg.delete()

                    for msg in messages:
                        if not msg:
                            continue
                            
                        caption = ""
                        if msg.caption:
                            caption = msg.caption.html
                        if bool(CUSTOM_CAPTION) and bool(msg.document):
                            caption = CUSTOM_CAPTION.format(
                                previouscaption=caption,
                                filename=msg.document.file_name
                            )

                        reply_markup = msg.reply_markup if not DISABLE_CHANNEL_BUTTON else None

                        try:
                            await msg.copy(
                                chat_id=message.from_user.id,
                                caption=caption,
                                parse_mode=ParseMode.HTML,
                                reply_markup=reply_markup,
                                protect_content=PROTECT_CONTENT
                            )
                            await asyncio.sleep(0.5)
                        except FloodWait as e:
                            await asyncio.sleep(e.x)
                            await msg.copy(
                                chat_id=message.from_user.id,
                                caption=caption,
                                parse_mode=ParseMode.HTML,
                                reply_markup=reply_markup,
                                protect_content=PROTECT_CONTENT
                            )
                        except Exception as e:
                            logger.error(f"Error sending file to {user_id}: {e}")
                    return

            except Exception as e:
                logger.error(f"Error processing file request: {e}")
                await message.reply_text("<b>❌ Error processing your request</b>")

        # Show start message if no file request
        reply_markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("📢 Official Channel", url=client.invitelink)],
            [
                InlineKeyboardButton("ℹ️ About Bot", callback_data="about"),
                InlineKeyboardButton("❌ Close", callback_data="close")
            ]
        ])
        
        await message.reply_text(
            text=START_MSG.format(
                first=message.from_user.first_name,
                last=message.from_user.last_name or "",
                username=f"@{message.from_user.username}" if message.from_user.username else "N/A",
                mention=message.from_user.mention,
                id=message.from_user.id
            ),
            reply_markup=reply_markup,
            disable_web_page_preview=True,
            quote=True
        )

    except Exception as e:
        logger.error(f"Error in start command: {e}", exc_info=True)

@Bot.on_message(filters.command('start') & filters.private)
async def not_joined(client: Client, message: Message):
    try:
        # Verification check for non-subscribers
        if VERIFY and not await check_verification(client, message.from_user.id):
            btn = [
                [InlineKeyboardButton("🔐 Verify Now", url=await get_token(client, message.from_user.id, f"https://telegram.me/{BOT_USERNAME}?start="))],
                [InlineKeyboardButton("❓ How To Verify", url=VERIFY_TUTORIAL)]
            ]
            return await message.reply_text(
                text="<b>🔒 VERIFICATION REQUIRED</b>\n\nYou must verify before accessing any content!",
                protect_content=True,
                reply_markup=InlineKeyboardMarkup(btn)
        
        # Channel join prompt
        buttons = [
            [InlineKeyboardButton("📢 Join Channel", url=client.invitelink)]
        ]
        
        if len(message.command) > 1:
            buttons.append([
                InlineKeyboardButton(
                    text='🔄 Try Again',
                    url=f"https://t.me/{client.username}?start={message.command[1]}"
                )
            ])

        await message.reply(
            text=FORCE_MSG.format(
                first=message.from_user.first_name,
                last=message.from_user.last_name or "",
                username=f"@{message.from_user.username}" if message.from_user.username else "N/A",
                mention=message.from_user.mention,
                id=message.from_user.id
            ),
            reply_markup=InlineKeyboardMarkup(buttons),
            quote=True,
            disable_web_page_preview=True
        )
    except Exception as e:
        logger.error(f"Error in not_joined handler: {e}", exc_info=True)

@Bot.on_callback_query(filters.regex("^get_verify$"))
async def get_new_verify_link(client: Bot, query: CallbackQuery):
    try:
        verify_url = await get_token(client, query.from_user.id, f"https://t.me/{BOT_USERNAME}?start=")
        await query.message.edit_text(
            text=f"""<b>🔗 New Verification Link Generated</b>

<i>Click below to verify:</i>
{verify_url}""",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ I've Verified", callback_data="start")],
                [InlineKeyboardButton("❓ Need Help?", url=VERIFY_TUTORIAL)]
            ]),
            disable_web_page_preview=True
        )
    except Exception as e:
        logger.error(f"Error generating verify link: {e}")
        await query.answer("❌ Failed to generate link. Please try again.", show_alert=True)

# [Rest of your existing code for users, broadcast commands...]
