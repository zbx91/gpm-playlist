import datetime
import os

from google.appengine.api import users
from google.appengine.ext import ndb

from django.http import HttpResponse
from django.shortcuts import render

import requests

from core import crypt

google_path = os.path.join(os.path.split(os.path.dirname(__file__))[0], 'sitepackages', 'google')
import google
google.__path__.append(google_path)

import gmusicapi

from . import models

# Create your views here.

def index(request):
    context = {}
    return render(request, 'manager/index.html', context)


def user(request):
    user = users.get_current_user()
    resp = '''
    <html>
        <head>User Info</head>
        <body>
            <pre>
                users.get_current_user() = {user}
                    - auth_domain = {auth_domain!r}
                    - email = {email!r}
                    - nickname = {nickname!r}
                    - user_id = {user_id!r}
                    - federated_identity = {federated_identity!r}
                    - federated_provider = {federated_provider!r}
                    - dir(user) = {items!r}
            </pre>
        </body>
    </html>
    '''.format(user=user, auth_domain=user.auth_domain(), email=user.email(), nickname=user.nickname(), user_id=user.user_id(), federated_identity=user.federated_identity(), federated_provider=user.federated_provider(), items=dir(user))
    
    return HttpResponse(resp)
    
def setpassword(request):
    clear_passwd = request.GET['pw']
    encrypted_passwd = crypt.encrypt(clear_passwd)
    user = users.get_current_user()
    
    entity = models.User(id=user.email(), password=encrypted_passwd)
    entity.put()
    
    return HttpResponse("Done.")
    
def testsongs(request):
    user = users.get_current_user()
    key = ndb.Key(models.User, user.email())
    entity = key.get()
    encrypted_passwd = entity.password
    clear_passwd = crypt.decrypt(encrypted_passwd)
    api = gmusicapi.Mobileclient(debug_logging=False)
    api.login(user.email(), clear_passwd, '364911a76fe0ffa1')  # gmusicapi.Mobileclient.FROM_MAC_ADDRESS)
    nin_albums = set(song['album'] for batch in api.get_all_songs(incremental=True) for song in batch if song['artist'] == 'Nine Inch Nails')
    from pprint import pformat
    resp = "<html><head></head><body><pre>{albums}</pre></body></html>".format(albums=pformat(nin_albums))
    return HttpResponse(resp)
    
def testssl(request):
    s = requests.Session()
    r = s.get('https://google.com')
    return HttpResponse(r.text)
    
    
def load_library(request):
    user= users.get_current_user()
    key = ndb.Key(models.User, user.email())
    entity = key.get()
    encrypted_passwd = entity.password
    clear_passwd = crypt.decrypt(encrypted_passwd)
    api = gmusicapi.Mobileclient(debug_logging=False)
    api.login(user.email(), clear_passwd, '364911a76fe0ffa1')
    track_gen = (song for batch in api.get_all_songs(incremental=True) for song in batch)
    artists = {}
    albums = {}
    entity_batch = []
    for count, track in enumerate(track_gen):
        if count and not count % 1000:
            ndb.put_multi(entity_batch)
            entity_batch = []
            
        try:
            if track['artistId'] and track['artistId'][0] not in artists:
                artist_data = {'id': track['artistId'][0], 'name': track['artist']}
    
                try:
                    artist_data['art'] = track['artistArtRef'][0]['url']
                    
                except (KeyError, IndexError):
                    pass
            
            artists[track['artistId'][0]] = models.Artist(**artist_data)
        except KeyError:
            pass

        if track['albumId'] and track['albumId'] not in albums:
            album_data = {'id': track['albumId'], 'name': track['album']}

            try:
                album_data['art'] = track['albumArtRef'][0]['url']
                
            except (KeyError, IndexError):
                pass
            
            albums[track['albumId']] = models.Album(**album_data)
            
        entity_data = {
            'id': track['id'],
            'title': track['title'],
            'created': datetime.datetime.fromtimestamp(int(track['creationTimestamp']) / 1000000),
            'modified': datetime.datetime.fromtimestamp(int(track['lastModifiedTimestamp']) / 1000000),
            'play_count': int(track.get('playCount', 0)),
            'duration_millis': int(track['durationMillis']),
            'rating': int(track.get('rating', 0)),
            'artist': track['artistId'][0],
            'album': track['albumId'],
        }
        
        try:
            entity_data['disc_number'] = int(track['discNumber'])
        except KeyError:
            pass
        
        try:
            entity_data['total_disc_count'] = int(track['totalDiscCount'])
        except KeyError:
            pass
        
        try:
            entity_data['track_number'] = int(track['trackNumber'])
        except KeyError:
            pass
        
        try:
            entity_data['total_track_count'] = int(track['totalTrackCount'])
        except KeyError:
            pass
        
        try:
            entity_data['album_artist'] = track['albumArtist']
        except KeyError:
            pass
        
        try:
            entity_data['year'] = int(track['year'])
        except KeyError:
            pass
        
        try:
            entity_data['composer'] = track['composer']
        except KeyError:
            pass
        
        try:
            entity_data['genre'] = track['genre']
        except KeyError:
            pass
        
        try:
            entity_data['comment'] = track['comment']
        except KeyError:
            pass
        
        entity_batch.append(models.Track(**entity_data))

    if entity_batch:
        ndb.put_multi(entity_batch)
        
    ndb.put_multi(artists.values())
    ndb.put_multi(albums.values())
    
    return HttpResponse('<html><body><ul><li>Tracks: {tracks}</li><li>Artists: {artists}</li><li>Albums: {albums}</li></ul></body></html>'.format(
        tracks=count + 1,
        artists=len(artists),
        albums=len(albums),
    ))