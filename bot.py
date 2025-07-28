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
from config import SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET, BOT_TOKEN, INTERVAL_SECONDS


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


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Hello! Use /add to add a playlist to monitor.")


async def add_playlist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Please send me a link to Spotify playlist")
    return ADD_2


async def manage_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # handle if it is private?

    playlist_link = update.message.text
    # https://open.spotify.com/playlist/68QIzP5hU03BK4EIUDPt6P?si=e9084b5de0764492
    playlist_url = playlist_link.split("/")[-1]
    if "?" in playlist_url:
        playlist_url = playlist_url.split("?")[0]
    if not sp.playlist(
        playlist_url
    ):  # check if playlist exists, not sure if this works
        await update.message.reply_text("Invalid playlist link. Please try again")
        return ADD_2

    # check if user in db, create if not
    user = User.select().where(User.telegram_id == update.effective_user.id).first()
    if not user:
        user = User.create(telegram_id=update.effective_user.id)

    # check if playlist in db, create if not
    playlist = Playlist.select().where(Playlist.url == playlist_url).first()
    now_utc = datetime.now(timezone.utc).replace(microsecond=0).replace(tzinfo=None)

    if not playlist:
        playlist_info = sp.playlist(playlist_url)
        playlist = Playlist.create(
            url=playlist_url,
            title=playlist_info["name"],
            last_added=now_utc,  # hack, but it's fine for now
        )
    # print(f"now_utc: {now_utc}")
    # print new playlist info from database
    logging.info(
        f"New playlist added: {playlist.title} {playlist.url} {playlist.last_added}"
    )

    # check if user is already monitoring the playlist
    monitored_playlist = (
        MonitoredPlaylist.select()
        .where(MonitoredPlaylist.user == user, MonitoredPlaylist.playlist == playlist)
        .first()
    )
    if not monitored_playlist:
        MonitoredPlaylist.create(user=user, playlist=playlist)

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
        if response[-1]:
            datetime_responce = datetime.strptime(
                response[-1]["added_at"], "%Y-%m-%dT%H:%M:%SZ"
            )
            for track in response:
                track_date = datetime.strptime(track["added_at"], "%Y-%m-%dT%H:%M:%SZ")
                if track_date > datetime_responce:
                    datetime_responce = track_date

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

    application = ApplicationBuilder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(add_conv_handler)

    job_queue = application.job_queue
    job_queue.run_repeating(
        callback=auto_check_playlist,
        first=20,  # seconds, but could be datetime with timezone (calculate at start so that it runs at a specific time)
        interval=INTERVAL_SECONDS,  # seconds
    )

    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
