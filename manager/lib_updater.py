'''
Simple module handling the processing of track libraries. This works with the
GAE taskqueue system, relying on the deferred.defer() function that places tasks
on the taskqueue quickly and easily.

This follows a very specific set of steps:

    1. Delete all existing track entities in the models.Track model for the
       given user.
    2. Change the 'exists' property for all entities in the models.TrackLists
       model for the given user to False.
    3. Load and process all tracks from Google Play Music for the given user,
       placing them into the models.Track model, and setting them in the
       models.TrackLists model with exists = True.
    4. Delete all entities in models.TrackLists for the given user with
       exists = False.
       
This also keeps track of the number of tracks that were loaded, as well as when
the library loading started & stopped (plus if it is in the midst of loading
currently)

.. note:: 

    There is a cron job that starts loading all of the libraries for all users
    at midnight (Google Time, IE: Pacific Time). This is an expensive process,
    with a lot of Datastore writes happening As a result, when/if the app
    becomes public, this might require ther to be a fee for users to actually
    use this service, just to pay the bill.
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
google_path = os.path.join(os.path.split(os.path.dirname(__file__))[0], 'sitepackages', 'google')
google.__path__.append(google_path)

import gmusicapi
import gmusicapi.protocol.mobileclient


from core import crypt
from . import models

def remove_bad_track_list_entries(user_id):
    batch_size = 750
    logging.info('Attempting to erase {size} bad track list entries from library...'.format(size=batch_size))
    keys = models.TrackLists.query(ndb.AND(models.TrackLists.user == user_id, models.TrackLists.exists == False)).fetch(batch_size, keys_only=True)
    futures = ndb.delete_multi_async(keys)
    ndb.Future.wait_all(futures)
    if keys:
        logging.info('Erased {num} bad track lists entries, attempting to erase more...'.format(num=len(keys)))
        deferred.defer(remove_bad_track_list_entries, user_id)
        
    else:
        logging.info('Erased all bad track list entries from library.')
        key = ndb.Key(models.User, user_id)
        entity = key.get()
        entity.updating = False
        entity.update_stop = datetime.datetime.now()
        entity.put()
        logging.info('Library updating complete.')


def load_batch(user_id, chunk, final):
    logging.info('Processing chunk: {chunk} tracks'.format(chunk=len(chunk)))
    batch = []

    for track in chunk:
        entity = models.Track(
            id=track['id'],
            user=user_id,
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
        
        logging.debug('Entry:\n{data}'.format(data=entity))
        
        batch.append(entity)
        
        list_entity = models.TrackLists(id=track['id'], user=user_id, exists=True)
        batch.append(list_entity)

    logging.info('Putting {num} tracks into datastore.'.format(num=len(batch) // 2))
    futures = ndb.put_multi_async(batch)

    ndb.Future.wait_all(futures)
    logging.info('Completed batch: {count} tracks processed.'.format(count=len(batch) // 2))
    
    if final is not None:
        key = ndb.Key(models.User, user_id)
        entity = key.get()
        entity.num_tracks = final
        entity.put()
        logging.info('All batches completed, total tracks processed: {num_tracks}'.format(num_tracks=final))
        logging.info('Now removing bad track list entries...')
        deferred.defer(remove_bad_track_list_entries, user_id)


@contextlib.contextmanager
def musicapi_connector(user_id, encrypted_passwd):
    key = ndb.Key(models.User, user_id)
    user = key.get()
    user_email = crypt.decrypt(user.email, user_id)
    clear_passwd = crypt.decrypt(encrypted_passwd, user_id)
    api = gmusicapi.Mobileclient(debug_logging=False)
    try:
        api.login(user_email, clear_passwd, get_random_string(16, '1234567890abcdef'))
        yield api
    finally:
        api.logout()


def get_batch(user_id, encrypted_passwd, _token=None, _num=1, _num_tracks=0):
    logging.info('Getting batch #{num}'.format(num=_num))
    chunk_size = 100
    with musicapi_connector(user_id, encrypted_passwd) as api:
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
    deferred.defer(load_batch, user_id, batch, final_track_count)
    if new_token is not None:
        deferred.defer(get_batch, user_id, crypt.encrypt(crypt.decrypt(encrypted_passwd, user_id), user_id), _token=new_token, _num=_num+1, _num_tracks=_num_tracks)
    logging.info('Batch #{num} loaded, {chunk_size} tracks queued for processing, {num_tracks} tracks total.'.format(num=_num, chunk_size=len(batch), num_tracks=_num_tracks))


def mark_track_lists(user_id, encrypted_passwd):
    batch_size = 600
    logging.info('Attempting to update {size} track list entries in library...'.format(size=batch_size))

    entities = models.Track.query(ndb.AND(models.TrackLists.user == user_id, models.TrackLists.exists == True)).fetch(batch_size)
    tuple(setattr(entity, 'exists', False) for entity in entities)
    futures = ndb.put_multi_async(entities)
    ndb.Future.wait_all(futures)
    
    if entities:
        logging.info('Update {num} tracks, attempting to update more...'.format(num=len(entities)))
        deferred.defer(mark_track_lists, user_id, crypt.encrypt(crypt.decrypt(encrypted_passwd, user_id), user_id))

    else:
        logging.info('Updated all track list entries, now loading library...')
        deferred.defer(get_batch, user_id, crypt.encrypt(crypt.decrypt(encrypted_passwd, user_id), user_id))


def erase_library(user_id, encrypted_passwd):
    batch_size = 750
    logging.info('Attempting to erase {size} tracks from library...'.format(size=batch_size))
    keys = models.Track.query(models.Track.user == user_id).fetch(batch_size, keys_only=True)
    futures = ndb.delete_multi_async(keys)
    ndb.Future.wait_all(futures)
    if keys:
        logging.info('Erased {num} tracks, attempting to erase more...'.format(num=len(keys)))
        deferred.defer(erase_library, user_id, crypt.encrypt(crypt.decrypt(encrypted_passwd, user_id), user_id))
    else:
        logging.info('Erased track library, now updating track lists entries...')
        deferred.defer(mark_track_lists, user_id, crypt.encrypt(crypt.decrypt(encrypted_passwd, user_id), user_id))