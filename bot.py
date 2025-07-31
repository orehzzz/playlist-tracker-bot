import logger
import logging
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

from database import User, Playlist, MonitoredPlaylist
from config import *


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
    await update.message.reply_text("Stopping current dialogue.")

    return ConversationHandler.END


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Hello! Use /add to add a playlist to monitor.")


async def add_playlist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Please send me a link to Spotify playlist")
    return ADD_2


async def manage_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Check the provided link and save all data to the db."""
    playlist_link = update.message.text

    # strip front and back of a link
    try:
        playlist_url = playlist_link.split("/")[-1]
        if "?" in playlist_url:
            playlist_url = playlist_url.split("?")[0]
    except IndexError:
        pass

    # check if playlist exists on Spotify
    try:
        playlist_info = sp.playlist(playlist_url)
    except spotipy.SpotifyException as e:
        if e.code == 404:
            await update.message.reply_text("Playlist not found (maybe it is private?)")
        else:
            await update.message.reply_text("Invalid playlist link. Please try again")
        return ADD_2

    # check if user in db, create if not
    user, created = User.get_or_create(
        telegram_id=update.effective_user.id,
        defaults={"name": update.effective_user.name},
    )
    if created:
        logging.info(
            f"New user added with telegram_id: {user.telegram_id}, name: {user.name}."
        )

    # check if playlist in db, create if not
    now_utc = datetime.now(timezone.utc).replace(microsecond=0).replace(tzinfo=None)
    playlist, created = Playlist.get_or_create(
        url=playlist_url,
        defaults={
            "title": playlist_info["name"],
            "last_added": now_utc,
        },
    )
    if created:
        logging.info(
            f"New playlist added by {user.name}: {playlist.title}, {playlist.url}, {playlist.last_added}"
        )

    # create a junction
    junction, created = MonitoredPlaylist.get_or_create(user=user, playlist=playlist)
    if created:
        logging.info(f"User {user.name} started monitoring playlist {playlist.name}")

    await update.message.reply_text(
        "Playlist added successfully! I will notify you when new songs are added to it"
    )


add_conv_handler = ConversationHandler(
    entry_points=[CommandHandler("add", add_playlist)],
    states={ADD_2: [MessageHandler(filters.TEXT & (~filters.COMMAND), manage_add)]},
    fallbacks=[
        MessageHandler(filters.COMMAND, stop),
    ],
    allow_reentry=True,
)


def request_all_tracks(playlist_id):
    logging.info(f"Requesting all tracks from playlist {playlist_id}")
    tracks = []
    results = sp.playlist_tracks(
        playlist_id,
        fields="items.track.name, items.track.id, items.added_at",
        limit=100,
    )  # Max limit is 100
    tracks.extend(results["items"])

    try:
        while results["next"]:  # Check if more tracks exist
            results = sp.next(results)
            tracks.extend(results["items"])
    except KeyError:
        logging.info("No more tracks found or reached the end of the playlist.")

    return tracks


async def auto_check_playlist(context: ContextTypes.DEFAULT_TYPE):

    for playlist in Playlist.select():
        playlist_url = playlist.url
        response = request_all_tracks(
            playlist_url
        )  ###########returns not response format? fix!#############################################################

        print(response)
        # get the timestamp when the last song was added to the playlist
        try:
            datetime_responce = datetime.strptime(
                response[-1]["added_at"], "%Y-%m-%dT%H:%M:%SZ"
            )
            for track in response:
                track_date = datetime.strptime(track["added_at"], "%Y-%m-%dT%H:%M:%SZ")
                if track_date > datetime_responce:
                    datetime_responce = track_date
        except IndexError:
            pass

        try:
            datetime_db = playlist.last_added
        except Exception as e:
            logging.error(f"Error: {e}")
            return

        # print(f"response: {datetime_responce}")
        # print(f"db: {datetime_db}")

        playlist_name = playlist.title or "Unknown Playlist"

        # compare it with the latest song in the playlist
        if datetime_db < datetime_responce:
            logging.info(
                f"New songs found in {playlist_name} ({playlist_url}) since last check"
            )
            playlist_id = playlist.id
            # save new latest_added to the db
            Playlist.update(last_added=datetime_responce).where(
                Playlist.id == playlist_id
            ).execute()
            # send a message to the users which have subscribed to this playlist
            users = MonitoredPlaylist.select().where(
                MonitoredPlaylist.playlist == playlist_id
            )
            for user in users:
                await context.bot.send_message(
                    user.user.telegram_id, f"Something new in {playlist_name}!"
                )
        else:
            logging.info(
                f"No new songs in {playlist_name} ({playlist_url}) since last check"
            )


def main() -> None:
    """Run the bot."""

    application = ApplicationBuilder().token(BOT_TOKEN).post_init(post_init).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(add_conv_handler)

    job_queue = application.job_queue
    job_queue.run_repeating(
        callback=auto_check_playlist,
        first=20,  # seconds
        interval=INTERVAL_SECONDS,
    )

    application.run_webhook(
        listen=WEBHOOK_LISTEN,
        port=WEBHOOK_PORT,
        webhook_url=WEBHOOK_URL,
        allowed_updates=Update.ALL_TYPES,
    )


async def post_init(application: ApplicationBuilder) -> None:
    """Post initialization function for the bot.

    Set bot's name, short/long description and commands.
    """
    # Comment this if you need to restart the bot several times
    await application.bot.set_my_name("PLaylistTrackerBot")
    await application.bot.set_my_short_description("Monitor your favourite playlists!")
    await application.bot.set_my_description(
        "Wellcome!\n\n"
        "This bot monitors playlists of your choise and will notify you when something new is added to them.\n\n"
        "Notifications may take a few minutes to appear after a new song is added."
    )

    # /start is excluded from the commands list
    await application.bot.set_my_commands(
        [
            ("add", "add a playlist"),
            # ("delete", "delete a playlist"),
            ("stop", "dissrupt current dialogue"),
        ]
    )


if __name__ == "__main__":
    main()
