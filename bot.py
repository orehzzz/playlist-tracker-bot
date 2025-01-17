import logging
import configparser
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ConversationHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

config = configparser.ConfigParser()
config.read("config.ini")

SPOTIFY_CLIENT_ID = config["Spotify"]["client_id"]
SPOTIFY_CLIENT_SECRET = config["Spotify"]["client_secret"]
BOT_TOKEN = config["Telegram"]["bot_token"]
CREATOR_ID = config["Telegram"]["creator_id"]


# Spotify API setup
client_credentials_manager = SpotifyClientCredentials(
    client_id=SPOTIFY_CLIENT_ID, client_secret=SPOTIFY_CLIENT_SECRET
)
sp = spotipy.Spotify(client_credentials_manager=client_credentials_manager)

ADD_2 = range(1)


async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Stop current conversation

    Use as a fallback function in handlers
    """
    logging.info(f"User {update.effective_user.id} stopped the conversation")
    return ConversationHandler.END


async def start(update: Update):
    await update.message.reply_text(
        "Hello! Send me a link to Spotify playlist to get started"
    )
    return ADD_2


async def add_playlist(update: Update):
    await update.message.reply_text("Please send me a link to Spotify playlist")
    return ADD_2


async def manage_add(update: Update, context):
    playlist_link = update.message.text
    playlist_id = playlist_link.split("/")[-1]
    context.user_data["playlist_id"] = playlist_id
    await update.message.reply_text(
        "Playlist added successfully! I will notify you when new songs are added to it"
    )


add_conv_handler = ConversationHandler(
    entry_points=[
        CommandHandler("add_playlist", add_playlist),
        CommandHandler("start", start),
    ],
    states={ADD_2: [MessageHandler(filters.TEXT & (~filters.COMMAND), manage_add)]},
    fallbacks=[
        MessageHandler(filters.COMMAND, stop),
    ],
    allow_reentry=True,
)


async def auto_check_playlist(context: ContextTypes.DEFAULT_TYPE):
    # for each playlist in db check if new songs are added
    print("Checking playlist")
    return 0


def main() -> None:
    """Run the bot."""

    application = ApplicationBuilder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(add_conv_handler)

    job_queue = application.job_queue
    job_queue.run_repeating(
        callback=auto_check_playlist,
        first=5,  # seconds, but could be datetime with timezone (calculate at start so that it runs at a specific time)
        interval=60,  # seconds
    )

    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
