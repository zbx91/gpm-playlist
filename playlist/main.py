import pathlib

import arrow
from gmusicapi import Mobileclient

from playlist.sql import lib as sqllib

pw_file = pathlib.Path('../apppw')

api = Mobileclient()
with pw_file.open() as f:
    print('Logging in with mobile client...')
    logged_in = api.login(
        'chill@darkhelm.org',
        f.read().strip(),
        Mobileclient.FROM_MAC_ADDRESS
    )

print(f'Logged in? {logged_in}')

songs = api.get_all_songs()

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


sqllib.erase_new_tracks()
sqllib.load_tracks(tracks)
