import calendar
import datetime
import itertools
import json
import logging
import pprint
import time
import urllib

from google.appengine.api import users
from google.appengine.ext import deferred
from google.appengine.ext import ndb

from django.http import HttpResponse
from django.shortcuts import render

import requests

from core import crypt, lib
from playlist import models


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
    '''.format(
        user=user,
        auth_domain=user.auth_domain(),
        email=user.email(),
        nickname=user.nickname(),
        user_id=user.user_id(),
        federated_identity=user.federated_identity(),
        federated_provider=user.federated_provider(),
        items=dir(user)
    )

    return HttpResponse(resp)


def setpassword(request):
    user = users.get_current_user()
    user_id = user.user_id()
    clear_passwd = request.GET['pw']
    encrypted_passwd = crypt.encrypt(clear_passwd, user_id)

    encrypted_email = crypt.encrypt(user.email(), user_id)
    entity = models.User(
        id=user_id,
        email=encrypted_email,
        password=encrypted_passwd
    )
    entity.put()

    return HttpResponse("Done.")


def erase_tracks(user_id):
    batch_size = 750
    logging.info(
        'Attempting to erase {size} tracks from library...'.format(
            size=batch_size
        )
    )
    parent_key = ndb.Key(urlsafe=user_id)
    keys = models.Track.query(ancestor=parent_key).fetch(
        batch_size,
        keys_only=True
    )
    futures = ndb.delete_multi_async(keys)
    ndb.Future.wait_all(futures)
    if keys:
        logging.info(
            'Erased {num} tracks, attempting to erase more...'.format(
                num=len(keys)
            )
        )
        deferred.defer(erase_tracks, user_id)
    else:
        logging.info('Erased all tracks from library.')
        logging.info('Library erasing complete.')


def erase_library(request):
    user = users.get_current_user()
    user_id = ndb.Key(models.User, user.user_id())
    logging.info('Library erasing starting...')
    deferred.defer(erase_tracks, user_id.urlsafe())
    return HttpResponse(
        ' '.join((
            '<html><body><p>Starting to erase library',
            'for user {user}</p></body></html>'
        )).format(user=user.email())
    )

def get_tracks(request):
    user = users.get_current_user()
    user_id = ndb.Key(models.User, user.user_id())
    query = models.Track.query(ancestor=user_id)
    cursor = None
    with lib.suppress(KeyError):
        cursor = ndb.Cursor(urlsafe=request.GET['next_page'])
    batch_size = 100
    with lib.suppress(KeyError):
        batch_size = int(request.GET['batch_size'])

    track_batch, next_cursor, more = query.fetch_page(
        batch_size,
        start_cursor=cursor
    )

    return HttpResponse(
        json.dumps({
            'next_page': next_cursor.urlsafe(),
            'more_tracks': more,
            'tracks': tuple(
                {
                    'id': track.key.id(),
                    'title': track.title,
                    'disc_number': track.disc_number,
                    'total_disc_count': track.total_disc_count,
                    'track_number': track.track_number,
                    'total_track_count': track.total_track_count,
                    'artist': track.artist,
                    'artist_art': track.artist_art,
                    'album_artist': track.album_artist,
                    'album': track.album,
                    'album_art': track.album_art,
                    'year': track.year,
                    'composer': track.composer,
                    'genre': track.genre,
                    'created': int(
                        calendar.timegm(
                            track.created.timetuple()
                        ) * 1000 + track.created.microsecond / 1000
                    ),
                    'modified': int(
                        calendar.timegm(
                            track.modified.timetuple()
                        ) * 1000 + track.modified.microsecond / 1000
                    ),
                    'play_count': track.play_count,
                    'duration_millis': track.duration_millis,
                    'rating': track.rating,
                    'comment': track.comment,
                    'partition': track.partition,
                    'holidays': tuple(holiday for holiday in track.holidays),
                }
                for track in track_batch
            ),
        }),
        content_type='text/json'
    )


