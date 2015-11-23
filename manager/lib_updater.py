'''
Simple module handling the processing of track libraries. This works with the
GAE taskqueue system, relying on the deferred.defer() function that places tasks
on the taskqueue quickly and easily.

This follows a very specific set of steps:

    1. Load and process all tracks from Google Play Music for the given user,
       placing them into models.Track. This includes:
       a. Any tracks that have been modified since the last update
       b. Any tracks in the library that have not yet been loaded
    2. Remove deleted tracks
       
This also keeps track of the number of tracks that were loaded, as well as when
the library loading started & stopped (plus if it is in the midst of loading
currently)

.. note:: 

    There is a cron job that starts loading all of the libraries for all users
    at midnight (GMT). This is an expensive process, with a lot of Datastore
    writes happening As a result, when/if the app becomes public, this might
    require ther to be a fee for users to actually use this service, just to pay
    the bill.
'''

from __future__ import division

import contextlib
import datetime
import logging
import os

from django.utils.crypto import get_random_string

from google.appengine.ext import deferred
from google.appengine.ext import ndb

import google
google_path = os.path.join(
    os.path.split(os.path.dirname(__file__))[0],
    'sitepackages',
    'google'
)
google.__path__.append(google_path)

import gmusicapi
import gmusicapi.protocol.mobileclient


from core import crypt
from . import models


@contextlib.contextmanager
def suppress(*exceptions):
    try:
        yield
    except exceptions:
        pass


def make_entity(parent_key, track):
    entity = models.Track(
        parent=parent_key,
        id=track['id'],
        title=track['title'],
        created=datetime.datetime.utcfromtimestamp(
            int(track['creationTimestamp']) / 1000000
        ),
        modified=datetime.datetime.utcfromtimestamp(
            int(track['lastModifiedTimestamp']) / 1000000
        ),
        play_count=int(track.get('playCount', 0)),
        duration_millis=int(track['durationMillis']),
        rating=int(track.get('rating', 0)),
        artist=track['artist'],
        album=track['album'],
    )
    
    with suppress(KeyError, IndexError):
        entity.artist_art = track['artistArtRef'][0]['url']

    with suppress(KeyError, IndexError):
        entity.album_art = track['albumArtRef'][0]['url']

    with suppress(KeyError):
        entity.disc_number = int(track['discNumber'])
    
    with suppress(KeyError):
        entity.total_disc_count = int(track['totalDiscCount'])
    
    with suppress(KeyError):
        entity.track_number = int(track['trackNumber'])
    
    with suppress(KeyError):
        entity.total_track_count = int(track['totalTrackCount'])
    
    with suppress(KeyError):
        entity.album_artist = track['albumArtist']
    
    with suppress(KeyError):
        entity.year = int(track['year'])
    
    with suppress(KeyError):
        entity.composer = track['composer']
    
    with suppress(KeyError):
        entity.genre = track['genre']
    
    with suppress(KeyError):
        entity.comment = track['comment']
    
    logging.debug('Entry:\n{data}'.format(data=entity))
    
    return entity


@ndb.transactional
def update_num_tracks(user_id, num):
    entity = ndb.Key(urlsafe=user_id).get()
    entity.num_tracks += num
    entity.put()


def load_batch(user_id, start, chunk, final):
    '''
    Loads a batch of tracks into models.Track entities.
    '''
    logging.info('Processing chunk: {chunk} tracks'.format(chunk=len(chunk)))
    batch = []
    deletes = []
    check_keys = []

    parent_key = ndb.Key(urlsafe=user_id)  # Library tracks tied to a user.

    for track in chunk:
        if track['deleted']:
            logging.debug('Deleting track: {id}'.format(id=track['id']))
            deletes.append(
                ndb.Key(
                    flat=[models.Track, track['id']],
                    parent=parent_key
                )
            )
            
        elif int(track['lastModifiedTimestamp']) >= start:
            batch.append(make_entity(parent_key, track))
            
        else:
            check_keys.append(
                ndb.Key(
                    flat=[models.Track, track['id']],
                    parent=parent_key
                )
            )

    if check_keys:
        existing_ids = set(
            item.key.id()
            for item in ndb.get_multi(check_keys)
        )
        check_ids = set(item.id() for item in check_keys)
        new_ids = tuple(check_ids - existing_ids)
        del existing_ids
        del check_ids
        new_track_gen = (
            track
            for track in chunk
            if track['id'] in new_ids
        )
        for track in new_track_gen:
            batch.append(make_entity(parent_key, track))

    logging.info(
        'Putting {num} tracks into datastore.'.format(
            num=len(batch)
        )
    )
    futures = ndb.put_multi_async(batch)
    
    if deletes:
        logging.info(
            'Deleting {num} tracks from datastore.'.format(
                num=len(deletes)
            )
        )
        futures.extend(ndb.delete_multi_async(deletes))

    ndb.Future.wait_all(futures)
    logging.info(
        'Completed batch: {count} tracks updated, {delcount} deleted.'.format(
            count=len(batch),
            delcount=len(deletes)
        )
    )
    
    update_num_tracks(user_id, len(chunk) - len(deletes))
    
    if final is not None:
        user_entity = parent_key.get()
        user_entity.updating = False
        user_entity.update_stop = datetime.datetime.now()
        user_entity.put()
        logging.info('All batches completed, library updated.')


@contextlib.contextmanager
def musicapi_connector(user_id, encrypted_passwd):
    '''
    Context manager that handles login/logout operations for Google Play Music
    using the gmusicapi.Mobileclient interface
    '''
    user = ndb.Key(urlsafe=user_id).get()
    uid = user.key.id()
    user_email = crypt.decrypt(user.email, uid)
    clear_passwd = crypt.decrypt(encrypted_passwd, uid)
    api = gmusicapi.Mobileclient(debug_logging=False)
    try:
        api.login(
            user_email,
            clear_passwd,
            get_random_string(16, '1234567890abcdef')
        )
        yield api
    finally:
        api.logout()


def get_batch(
    user_id,
    start,
    encrypted_passwd,
    _token=None,
    _num=1,
    _num_tracks=0
):
    '''
    Retrieves a batch of tracks from Google Play Music, to be processed.
    '''
    logging.info('Getting batch #{num}'.format(num=_num))
    chunk_size = 100
    num_batches = 10
    with musicapi_connector(user_id, encrypted_passwd) as api:
        for count in xrange(num_batches):
            results = api._make_call(
                gmusicapi.protocol.mobileclient.ListTracks,
                start_token=_token,
                max_results=chunk_size
            )
            _token = results.get('nextPageToken', None)
            results = tuple(
                item
                for item in results['data']['items']
            )
            _num_tracks += len(results)
            final_track_count = _num_tracks if _token is None else None
            logging.info(
                ' '.join((
                    'Batch #{num} loaded, {chunk_size} tracks queued',
                    'for processing, {num_tracks} tracks total.'
                )).format(
                    num=_num,
                    chunk_size=len(results),
                    num_tracks=_num_tracks
                )
            )
            _num += 1
            deferred.defer(load_batch, user_id, start, results, final_track_count)
            if _token is None:
                break
    if _token is not None:
        logging.info(
            'Preparing to retrieve more batches...'
        )
        uid = ndb.Key(urlsafe=user_id).id()
        deferred.defer(
            get_batch,
            user_id,
            start,
            crypt.encrypt(crypt.decrypt(encrypted_passwd, uid), uid),
            _token=_token,
            _num=_num+1,
            _num_tracks=_num_tracks
        )
