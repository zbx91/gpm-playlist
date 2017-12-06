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


@conn.trackdb.sessionize()
def get_current_tracks(*, session: sqlalchemy.orm.session.Session):
    query = conn.bakery(lambda s: s.query(tables.trackdb.NewTracks))
    return [
        {
            key: value
            for key, value in row.__dict__.items()
            if key in {
                col.name
                for col in tables.trackdb.NewTracks.__table__.c
            }
        }
        for row in query(session)
    ]


@conn.trackdb.sessionize()
def get_previous_tracks(*, session: sqlalchemy.orm.session.Session):
    query = conn.bakery(lambda s: s.query(tables.trackdb.Tracks))
    return [
        {
            key: value
            for key, value in row.__dict__.items()
            if key in {
                col.name
                for col in tables.trackdb.NewTracks.__table__.c
            }
        }
        for row in query(session)
    ]


@conn.trackdb.sessionize()
def set_password(username: str, password: str, *, session):
    creds = tables.trackdb.Credentials(username=username, password=password)
    print(creds)
    session.add(creds)


@conn.trackdb.sessionize()
def get_password(username: str, *, session) -> str:
    query = conn.bakery(lambda s: s.query(tables.trackdb.Credentials))
    query += lambda q: q.filter(username == sqlalchemy.bindparam('username'))
    return query(session).params(username=username).one().password
