from datetime import datetime

from peewee import (
    PostgresqlDatabase,
    Model,
    AutoField,
    CharField,
    TextField,
    DateTimeField,
    ForeignKeyField,
    CompositeKey,
)


db = PostgresqlDatabase(
    "postgres",
    user="postgres",
    password="postgres",
)


# Base model for setting up the database connection
class BaseModel(Model):
    class Meta:
        database = db


# Users Table
class User(BaseModel):
    id = AutoField()  # Auto-incrementing primary key
    telegram_id = CharField(unique=True)
    name = CharField(max_length=255, null=True)  # User's tag or name


# Playlists Table
class Playlist(BaseModel):
    id = AutoField()  # Auto-incrementing primary key
    url = TextField(unique=True)  # Playlist URL or unique identifier
    title = CharField(max_length=255, null=True)  # Playlist title
    last_added = DateTimeField(null=True)  # Timestamp of the last change or addition to the playlist


# Junction Table: MonitoredPlaylists
class MonitoredPlaylist(BaseModel):
    user = ForeignKeyField(User, backref="monitored_playlists", on_delete="CASCADE")
    playlist = ForeignKeyField(
        Playlist, backref="monitored_by_users", on_delete="CASCADE"
    )

    class Meta:
        primary_key = CompositeKey("user", "playlist")  # Composite primary key


# with db:
#     db.create_tables([User, Playlist, MonitoredPlaylist])
#     db.drop_tables([User, Playlist, MonitoredPlaylist])
