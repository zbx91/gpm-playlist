from __future__ import division

import contextlib
import datetime
import functools
import itertools
import logging
import os
import pprint
import time
import urllib

from google.appengine.api import users
from google.appengine.ext import deferred
from google.appengine.ext import ndb

from django.http import HttpResponse
from django.shortcuts import render
from django.utils.crypto import get_random_string

import requests

from core import crypt

google_path = os.path.join(os.path.split(os.path.dirname(__file__))[0], 'sitepackages', 'google')
import google
google.__path__.append(google_path)

import gmusicapi
import gmusicapi.protocol.mobileclient

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


def chunk_loader(user_email, chunk, final):
    logging.info('Processing chunk: {chunk} tracks'.format(chunk=len(chunk)))
    tracks = []

    for track in chunk:
        entity = models.Track(
            id=':'.join((user_email, track['id'])), # ID key contains user email and the track ID from google play music.
            title=track['title'],
            created=datetime.datetime.fromtimestamp(int(track['creationTimestamp']) / 1000000),
            modified=datetime.datetime.fromtimestamp(int(track['lastModifiedTimestamp']) / 1000000),
            play_count=int(track.get('playCount', 0)),
            duration_millis=int(track['durationMillis']),
            rating=int(track.get('rating', 0)),
            artist=track['artist'],
            album=track['album'],
        )
        
        try:
            entity.artist_art = track['artistArtRef'][0]['url']
        except (KeyError, IndexError):
            pass

        try:
            entity.album_art = track['albumArtRef'][0]['url']
        except (KeyError, IndexError):
            pass

        try:
            entity.disc_number = int(track['discNumber'])
        except KeyError:
            pass
        
        try:
            entity.total_disc_count = int(track['totalDiscCount'])
        except KeyError:
            pass
        
        try:
            entity.track_number = int(track['trackNumber'])
        except KeyError:
            pass
        
        try:
            entity.total_track_count = int(track['totalTrackCount'])
        except KeyError:
            pass
        
        try:
            entity.album_artist = track['albumArtist']
        except KeyError:
            pass
        
        try:
            entity.year = int(track['year'])
        except KeyError:
            pass
        
        try:
            entity.composer = track['composer']
        except KeyError:
            pass
        
        try:
            entity.genre = track['genre']
        except KeyError:
            pass
        
        try:
            entity.comment = track['comment']
        except KeyError:
            pass
        
        logging.info('Entry:\n{data}'.format(data=entity))
        
        tracks.append(entity)

    logging.info('Putting {num} tracks into datastore.'.format(num=len(tracks)))
    futures = ndb.put_multi_async(tracks)

    ndb.Future.wait_all(futures)
    logging.info('Completed batch: {count} tracks processed.'.format(count=len(tracks)))
    
    if final is not None:
        logging.info('All batches completed, total tracks processed: {num_tracks}'.format(num_tracks=final))


@contextlib.contextmanager
def musicapi_connector(user_email, encrypted_passwd):
    clear_passwd = crypt.decrypt(encrypted_passwd)
    api = gmusicapi.Mobileclient(debug_logging=False)
    try:
        api.login(user_email, clear_passwd, get_random_string(16, '1234567890abcdef'))
        yield api
    finally:
        api.logout()

def get_batch(user_email, encrypted_passwd, _token=None, _num=1, _num_tracks=0):
    logging.info('Getting batch #{num}'.format(num=_num))
    chunk_size = 200
    with musicapi_connector(user_email, encrypted_passwd) as api:
        results = api._make_call(gmusicapi.protocol.mobileclient.ListTracks, start_token=_token, max_results=chunk_size)
        new_token = results.get('nextPageToken', None)
        batch = tuple(
            item
            for item in results['data']['items']
            if not item.get('deleted', False)
        )
        del results
    _num_tracks += len(batch)
    final_track_count = _num_tracks if new_token is None else None
    deferred.defer(chunk_loader, user_email, batch, final_track_count)
    if new_token is not None:
        deferred.defer(get_batch, user_email, crypt.encrypt(crypt.decrypt(encrypted_passwd)), _token=new_token, _num=_num+1, _num_tracks=_num_tracks)
    logging.info('Batch #{num} loaded, {chunk_size} tracks queued for processing, {num_tracks} tracks total.'.format(num=_num, chunk_size=len(batch), num_tracks=_num_tracks))


def load_library(request):
    logging.info('Starting load_library()')
    user = users.get_current_user()
    user_email = user.email()
    key = ndb.Key(models.User, user_email)
    entity = key.get()
    encrypted_passwd = entity.password
    deferred.defer(get_batch, user_email, encrypted_passwd)
    logging.info('load_library() finished.')

    return HttpResponse('<html><body><p>Starting music loading process...</p></body></html>')