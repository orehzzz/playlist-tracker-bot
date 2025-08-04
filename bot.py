import logger
import logging
from datetime import datetime, timezone

import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ConversationHandler,
    ContextTypes,
    MessageHandler,
    filters,
    CallbackQueryHandler,
)

from database import User, Playlist, MonitoredPlaylist
from config import *


# Spotify API setup
client_credentials_manager = SpotifyClientCredentials(
    client_id=SPOTIFY_CLIENT_ID, client_secret=SPOTIFY_CLIENT_SECRET
)
sp = spotipy.Spotify(client_credentials_manager=client_credentials_manager)


MANAGE_ADD, MANAGE_DELETE = range(2)


async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Stop current conversation

    Use as a fallback function in conversation handlers
    """
    logging.info(
        f"User {update.effective_user.name} - {update.effective_user.id} stopped the conversation"
    )
    await update.message.reply_text("Stopping current dialogue.")

    return ConversationHandler.END


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """First command user is expected to execute"""
    await update.message.reply_text("Hi there! Use /add to start tracking a playlist.")


async def add_playlist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Initiate adding a playlist"""
    logging.info(
        f"User {update.effective_user.name} - {update.effective_user.id} started adding a playlist"
    )
    await update.message.reply_text("Please send the Spotify playlist link.")
    return MANAGE_ADD


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
        return MANAGE_ADD

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
            f"New playlist added: {playlist.title} - {playlist.url} - {playlist.last_added}"
        )
    else:
        logging.warning(
            f"User tried to add a playlist {playlist.title} - {playlist.url}, but it was already in db"
        )

    # check if user in db, create if not
    user, created = User.get_or_create(
        telegram_id=update.effective_user.id,
        defaults={"name": update.effective_user.name},
    )
    if created:
        logging.info(
            f"New user added with telegram_id: {user.telegram_id} - {user.name}"
        )

    # create a junction
    junction, created = MonitoredPlaylist.get_or_create(user=user, playlist=playlist)
    if created:
        logging.info(
            f"User {user.name} - {user.telegram_id} started monitoring playlist {playlist.title}"
        )

    await update.message.reply_text(
        "Playlist added successfully! I will notify you when new songs are added to it"
    )
    return ConversationHandler.END


add_conv_handler = ConversationHandler(
    entry_points=[CommandHandler("add", add_playlist)],
    states={
        MANAGE_ADD: [MessageHandler(filters.TEXT & (~filters.COMMAND), manage_add)]
    },
    fallbacks=[
        MessageHandler(filters.COMMAND, stop),
    ],
    allow_reentry=True,
)


async def delete_playlist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Initiate deleting a playlist"""
    logging.info(
        f"User {update.effective_user.name} - {update.effective_user.id} started deleting a playlist"
    )
    user = User.get(User.telegram_id == update.effective_user.id)

    keyboard = []
    junctions = MonitoredPlaylist.select().where(MonitoredPlaylist.user == user)
    for junction in junctions:
        keyboard.append(
            [
                InlineKeyboardButton(
                    junction.playlist.title, callback_data=junction.playlist.id
                )
            ]
        )
    # handle if no playlists
    if keyboard == []:
        await update.message.reply_text(
            "You don’t have any playlists yet. Add one with /add."
        )
        logging.info(
            f"User {update.effective_user.name} - {update.effective_user.id} tried to delete a playlist, but they don't have any"
        )
        return ConversationHandler.END

    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "Choose which playlist to delete:", reply_markup=reply_markup
    )
    return MANAGE_DELETE


async def manage_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Delete the chosen playlist or notify about failure"""
    query = update.callback_query
    await query.answer()

    playlist = Playlist.get_by_id(query.data)
    logging.info(
        f"User {update.effective_user.name} - {update.effective_user.id} is removing {playlist.title} - {playlist.url}"
    )

    user = User.get(User.telegram_id == update.effective_user.id)
    # delete junction
    deleted = (
        MonitoredPlaylist.delete()
        .where(
            (MonitoredPlaylist.playlist_id == playlist.id)
            & (MonitoredPlaylist.user == user)
        )
        .execute()
    )
    if not deleted:
        logging.error(
            f"User {update.effective_user.name} - {update.effective_user.id} failed to delete {playlist.title} - {playlist.url}"
        )
        await query.edit_message_text(
            "Something went wrong when deleting this playlist. Try again later"
        )
        return ConversationHandler.END

    # if playlist has no junctions - delete it
    remaining_junction = (
        MonitoredPlaylist.select()
        .where(MonitoredPlaylist.playlist_id == playlist.id)
        .exists()
    )
    if not remaining_junction:
        logging.info(
            f"No junctions left, deleting playlist {playlist.title} - {playlist.url}"
        )
        if Playlist.delete_by_id(playlist.id):
            logging.info(
                f"Playlist {playlist.title} - {playlist.url} successfully deleted"
            )

    await query.edit_message_text(f"Playlist {playlist.title} successfully deleted")
    return ConversationHandler.END


delete_conv_handler = ConversationHandler(
    entry_points=[CommandHandler("delete", delete_playlist)],
    states={MANAGE_DELETE: [CallbackQueryHandler(manage_delete)]},
    fallbacks=[
        MessageHandler(filters.COMMAND, stop),
    ],
    allow_reentry=True,
)


def request_all_tracks(playlist_url):
    """Get all tracks via spotify's API and return them as a list

    If request failed returns `False` and deletes playlist from db"""
    logging.info(f"Requesting all tracks from playlist {playlist_url}")
    tracks = []
    try:
        results = sp.playlist_tracks(
            playlist_url,
            fields="items.track.name, items.track.id, items.added_at",
            limit=100,
        )  # Max limit is 100
        tracks.extend(results["items"])
    except spotipy.exceptions.SpotifyException as e:
        if e.http_status == 404:
            playlist = Playlist.select().where(Playlist.url == playlist_url).first()
            if Playlist.delete_instance(playlist):
                logging.warning(
                    f"Playlist {playlist.title} - {playlist_url} was not found, so it was removed from db"
                )
        return False

    try:
        while results["next"]:  # Check if more tracks exist
            results = sp.next(results)
            tracks.extend(results["items"])
    except KeyError:
        logging.info(f"Requested all tracks from a playlist {playlist_url}.")

    return tracks


async def auto_check_playlist(context: ContextTypes.DEFAULT_TYPE):
    """Request playlists data and check when the last track was added"""
    for playlist in Playlist.select():
        playlist_url = playlist.url
        response = request_all_tracks(playlist_url)

        # skip if bad response
        if not response:
            continue

        # get the timestamp when the last song was added to the playlist
        try:
            datetime_response = datetime.strptime(
                response[-1]["added_at"], "%Y-%m-%dT%H:%M:%SZ"
            )
            for track in response:
                track_date = datetime.strptime(track["added_at"], "%Y-%m-%dT%H:%M:%SZ")
                if track_date > datetime_response:
                    datetime_response = track_date
        except IndexError:
            pass

        playlist_name = playlist.title or "'Unknown Playlist'"

        # compare it with the latest song in the playlist
        if playlist.last_added < datetime_response:
            logging.info(
                f"New songs found in {playlist_name} - {playlist_url} since last check"
            )

            # save new latest_added to the db
            playlist_id = playlist.id
            Playlist.update(last_added=datetime_response).where(
                Playlist.id == playlist_id
            ).execute()

            # send a message to the users which have subscribed to this playlist
            junctions = MonitoredPlaylist.select().where(
                MonitoredPlaylist.playlist == playlist_id
            )
            for junction in junctions:
                await context.bot.send_message(
                    junction.user.telegram_id,
                    f"Something new in [{playlist_name}](https://open.spotify.com/playlist/{playlist_url})",
                )
                logging.info(
                    f"User {junction.user.name} - {junction.user.telegram_id} notified"
                )
        else:
            logging.info(
                f"No new songs in {playlist_name} - {playlist_url} since last check"
            )


def main() -> None:
    """Run the bot."""

    application = ApplicationBuilder().token(BOT_TOKEN).post_init(post_init).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(add_conv_handler)
    application.add_handler(delete_conv_handler)

    job_queue = application.job_queue
    job_queue.run_repeating(
        callback=auto_check_playlist,
        first=20,
        interval=INTERVAL_SECONDS,
    )

    application.run_webhook(
        listen=WEBHOOK_LISTEN,
        port=WEBHOOK_PORT,
        webhook_url=WEBHOOK_URL,
        allowed_updates=Update.ALL_TYPES,
    )
    # application.run_polling(allowed_updates=Update.ALL_TYPES)


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
            ("delete", "delete a playlist"),
            ("stop", "dissrupt current dialogue"),
        ]
    )


if __name__ == "__main__":
    main()
