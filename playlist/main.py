import pathlib

from gmusicapi import Mobileclient

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

primary_video = [
    {
        subkey: subvalue
        for subkey, subvalue in value.items()
        if subkey != 'thumbnails'
    }
    for song in songs
    for key, value in song.items()
    if key == 'primaryVideo' and value
]

video_thumbnails = [
    dict(
        elem.items(),
        primary_video_id=value['id'],
    )
    for song in songs
    for key, value in song.items()
    if key == 'primaryVideo' and value
    for elem in value.get('thumbnails', [])
]

tracks = []

album_art = []

artist_id = []

artist_art = []


prime_num = 0

# for song in songs:
    # track = {}
    # for key, value in song.items():
        # if key == 'albumArtRef' and value:
        #     for elem in value:
        #         album_art.append({
        #             subkey: subvalue
        #             for subkey, subvalue in elem.items()
        #         })
        #     track[key] = value

        # elif key == 'artistArtRef' and value:
        #     for elem in value:
        #         artist_art.append({
        #             subkey: subvalue
        #             for subkey, subvalue in elem.items()
        #         })
        #     track[key] = value

        # elif key == 'artistId' and value:
        #     try:
        #         track['artistId'] = value[0]
        #     except IndexError:
        #         track['artistId'] = None

        # elif key == 'primaryVideo' and value:
        #     primary_video.append({
        #         subkey: subvalue
        #         for subkey, subvalue in value.items()
        #         # if subkey != 'thumbnails'
        #     })
        #     for elem in value['thumbnails']:
        #         thumbnail = {
        #             thumbkey: thumbvalue
        #             for thumbkey, thumbvalue in elem.items()
        #         }
        #         thumbnail['primary_video_id'] = prime_num
        #         video_thumbnails.append(thumbnail)
        #     track[key] = value
        # else:
        #     track[key] = value
    # tracks.append(track)

from pprint import pprint
# pprint(tracks)
# print('-'*79)
# pprint(album_art)
# print('-'*79)
# pprint(artist_id)
# print('-'*79)
# pprint(artist_art)
# print('-'*79)
pprint(primary_video)
print('-'*79)
pprint(video_thumbnails)
