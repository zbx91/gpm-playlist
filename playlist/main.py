import pathlib

from gmusicapi import Mobileclient

pw_file = pathlib.Path('../../apppw')

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

dict_info = {}

album_art_ref = {}

artist_id = {}

artist_art_ref = {}

primary_video = {}

for song in songs:
    for key, value in song.items():
        if key == 'albumArtRef' and value:
            for elem in value:
                for subkey, subvalue in elem.items():
                    try:
                        album_art_ref[subkey] |= {type(subvalue)}
                    except KeyError:
                        album_art_ref[subkey] = {type(subvalue)}

        elif key == 'artistArtRef' and value:
            for elem in value:
                for subkey, subvalue in elem.items():
                    try:
                        artist_art_ref[subkey] |= {type(subvalue)}
                    except KeyError:
                        artist_art_ref[subkey] = {type(subvalue)}

        elif key == 'artistId' and value:
            artist_id = {type(elem) for elem in value}

        elif key == 'primaryVideo' and value:
            for subkey, subvalue in value.items():
                try:
                    primary_video[subkey] |= {type(subvalue)}
                except KeyError:
                    primary_video[subkey] = {type(subvalue)}

        try:
            dict_info[key] |= {type(value)}
        except KeyError:
            dict_info[key] = {type(value)}

from pprint import pprint
pprint(dict_info)
print('-'*79)
pprint(album_art_ref)
print('-'*79)
pprint(artist_id)
print('-'*79)
pprint(artist_art_ref)
print('-'*79)
pprint(primary_video)
