"""Library of SQL functions to operate on the database."""

import typing

import sqlalchemy

from playlist.sql import conn, tables


@conn.trackdb.sessionize()
def erase_new_tracks(*, session: sqlalchemy.orm.session.Session):
    """Wipe the New Tracks table to reload it."""
    session.query(tables.trackdb.NewTracks).delete()


@conn.trackdb.sessionize()
def load_tracks(
    tracks: typing.List[typing.Dict[str, typing.Any]],
    *,
    session: sqlalchemy.orm.session.Session
) -> None:
    """Load tracks into table in the database."""
    inserts = (
        {
            key: value
            if key not in {
                'creationTimestamp',
                'lastModifiedTimestamp',
                'recentTimestamp',
                'recentTimestamp'
            }
            else value.datetime
            for key, value in track.items()
        }
        for track in tracks
    )
    session.bulk_insert_mappings(tables.trackdb.NewTracks, inserts)
