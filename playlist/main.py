from __future__ import generator_stop

import asyncio
import functools
import pprint
import typing

import arrow
import gmusicapi

from playlist.core import lib as corelib
from playlist.sql import lib as sqllib
from playlist.crypt import sync_lib as cryptlib
from playlist.pd import lib as pdlib

USERNAME = 'chill@darkhelm.org'

loop = asyncio.get_event_loop()

api = gmusicapi.Mobileclient()
print('Logging in with mobile client...')
logged_in = api.login(
    'chill@darkhelm.org',
    cryptlib.decrypt(sqllib.get_password(username=USERNAME)),
    gmusicapi.Mobileclient.FROM_MAC_ADDRESS
)
print('Logged in.')


@corelib.inject_loop
async def load_batch(
    songs: typing.List[typing.Dict[str, typing.Any]],
    *,
    loop: asyncio.AbstractEventLoop
) -> str:
    print(f'Processing {len(songs)} tracks.')
    tracks = [
        {
            key: value['id']
            if key == 'primaryVideo'
            else (value[0] if value else None)
            if key == 'artistId'
            else int(value)
            if key in {'durationMillis', 'estimatedSize', 'rating'}
            else arrow.get(int(value) / 1_000_000)
            if key in {
                'creationTimestamp',
                'lastModifiedTimestamp',
                'recentTimestamp',
                'recentTimestamp'
            }
            else value
            for key, value in song.items()
            if key not in {'albumArtRef', 'artistArtRef'}
        }
        for song in songs
    ]
    print(f'Processed {len(songs)} tracks, loading into SQL table.')
    await loop.run_in_executor(None, sqllib.load_tracks, tracks)
    print(f'Loaded {len(songs)} tracks into SQL table.')
    return f'Finished with {len(tracks)} tracks.'


@corelib.inject_loop
async def import_from_gpm(*, loop: asyncio.AbstractEventLoop) -> None:
    batch_iter = corelib.AsyncIterator(
        await loop.run_in_executor(
            None,
            functools.partial(api.get_all_songs, incremental=True)
        )
    )
    print('Clearing SQL table.')
    await loop.run_in_executor(None, sqllib.erase_new_tracks)
    tasks = [
        asyncio.ensure_future(load_batch(batch))
        async for batch in batch_iter
    ]
    for task in asyncio.as_completed(tasks):
        print(await task)

    curr_coro = loop.run_in_executor(None, sqllib.get_current_tracks)
    prev_coro = loop.run_in_executor(None, sqllib.get_previous_tracks)
    results = await pdlib.get_ins_upd_del('Tracks', curr_coro, prev_coro, 'id')
    pprint.pprint(results)

loop.run_until_complete(import_from_gpm())
