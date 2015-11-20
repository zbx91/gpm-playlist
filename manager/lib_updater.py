'''
Simple module handling the processing of track libraries. This works with the
GAE taskqueue system, relying on the deferred.defer() function that places tasks
on the taskqueue quickly and easily.

This follows a very specific set of steps:

    1. Load and process all tracks from Google Play Music for the given user,
       placing them into models.Track.
    2. Delete all un-touched tracks (no longer in library)
       
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


def clean_tracks(user_id, start):
    '''
    Erases a batch of models.Track entities for a given user from the datastore,
    if the entity was not touched in the last update.
    '''
    batch_size = 750
    logging.info(
        'Attempting to clean {size} deleted tracks from library...'.format(
            size=batch_size
        )
    )
    parent_key = ndb.Key(urlsafe=user_id)
    keys = models.Track.query(
        models.Track.touched < start,
        ancestor=parent_key
    ).fetch(batch_size, keys_only=True)
    futures = ndb.delete_multi_async(keys)
    ndb.Future.wait_all(futures)
    if keys:
        logging.info(
            'Cleaned {num} deleted tracks, attempting to clean more...'.format(
                num=len(keys)
            )
        )
        deferred.defer(clean_tracks, user_id, start)
        
    else:
        logging.info('Cleaned all deleted tracks from library.')
        entity = parent_key.get()
        entity.updating = False
        entity.update_stop = datetime.datetime.now()
        entity.put()
        logging.info('Library updating complete.')
        
def load_batch(user_id, start, chunk, final):
    '''
    Loads a batch of tracks into models.Track entities.
    '''
    logging.info('Processing chunk: {chunk} tracks'.format(chunk=len(chunk)))
    batch = []

    parent_key = ndb.Key(urlsafe=user_id)  # Library tracks tied to a user.

    for track in chunk:
        entity = models.Track(
            parent=parent_key,
            id=track['id'],
            title=track['title'],
            created=datetime.datetime.fromtimestamp(
                int(track['creationTimestamp']) / 1000000
            ),
            modified=datetime.datetime.fromtimestamp(
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
        
        batch.append(entity)

    logging.info(
        'Putting {num} tracks into datastore.'.format(
            num=len(batch)
        )
    )
    futures = ndb.put_multi_async(batch)

    ndb.Future.wait_all(futures)
    logging.info(
        'Completed batch: {count} tracks processed.'.format(
            count=len(batch)
        )
    )
    
    if final is not None:
        entity = parent_key.get()
        entity.num_tracks = final
        entity.put()
        logging.info(
            ' '.join((
                'All batches completed, total tracks',
                'processed: {num_tracks}'
            )).format(
                num_tracks=final
            )
        )
        logging.info('Now cleaning up tracks...')
        deferred.defer(clean_tracks, user_id, start)


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
    with musicapi_connector(user_id, encrypted_passwd) as api:
        results = api._make_call(
            gmusicapi.protocol.mobileclient.ListTracks,
            start_token=_token,
            max_results=chunk_size
        )
        new_token = results.get('nextPageToken', None)
        batch = tuple(
            item
            for item in results['data']['items']
            if not item.get('deleted', False)
        )
        del results
    _num_tracks += len(batch)
    final_track_count = _num_tracks if new_token is None else None
    deferred.defer(load_batch, user_id, start, batch, final_track_count)
    if new_token is not None:
        uid = ndb.Key(urlsafe=user_id).id()
        deferred.defer(
            get_batch,
            user_id,
            start,
            crypt.encrypt(crypt.decrypt(encrypted_passwd, uid), uid),
            _token=new_token,
            _num=_num+1,
            _num_tracks=_num_tracks
        )
    logging.info(
        ' '.join((
            'Batch #{num} loaded, {chunk_size} tracks queued',
            'for processing, {num_tracks} tracks total.'
        )).format(
            num=_num,
            chunk_size=len(batch),
            num_tracks=_num_tracks
        )
    )
