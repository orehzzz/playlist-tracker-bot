import logging
import configparser
import json
from datetime import datetime, timezone

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


# Config setup
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

    playlist_id = "1AA52Yoauv86t380F4HL2d"  # Misc.
    response = sp.playlist_items(
        playlist_id,
        fields="items.track.name, items.track.id, items.added_at",
    )

    latest_from_db = datetime(
        2021,
        1,
        1,
    )  # get the latest song from the db

    # get the timestamp when the last song was added to the playlist
    if response["items"][0]:
        latest_from_playlist = datetime.strptime(
            response["items"][0]["added_at"], "%Y-%m-%dT%H:%M:%SZ"
        )
        for track in response["items"]:
            track_date = datetime.strptime(track["added_at"], "%Y-%m-%dT%H:%M:%SZ")
            if track_date > latest_from_playlist:
                latest_from_playlist = track_date
                print(latest_from_playlist)

    # convert to utc
    latest_from_playlist.astimezone(timezone.utc)
    latest_from_playlist.replace(tzinfo=None)
    print(latest_from_playlist)

    # compare it with the latest song in the playlist
    if latest_from_db < latest_from_playlist:
        print("'Playlist' has a new song!")
        # save new latest_added to the db
        # send a message to the users which have subscribed to this playlist

    return ConversationHandler.END


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
