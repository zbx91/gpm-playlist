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

import base64
import contextlib
import datetime
import decimal
import hashlib
import itertools
import logging
import math
import operator
import os
import pprint

from Crypto.Random import random

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

from core import crypt, lib
from playlist import models


def to_datetime(timestamp_str):
    return datetime.datetime.utcfromtimestamp(int(timestamp_str) / 1000000)


def finalize_user(user_id, avg_length):
    '''
    Final updates to the User entity, storing statistics and ending the library
    update.
    '''

    user = ndb.Key(urlsafe=user_id).get()
    logging.info('Finalizing user {uid} library update.'.format(
        uid=user.key.id()
    ))

    user.avg_length = avg_length
    user.updating = False
    user.update_stop = datetime.datetime.now()
    del user.updated_batches
    del user.update_lengths
    user.put()
    logging.info(
        ' '.join((
            'Library updated{scores}, {num} tracks total,',
            'average length of {avglen}'
        )).format(
            scores=(
                ' ({num_deletes} deletes, {num_merges} updates)'.format(
                    num_deletes=user.num_deletes,
                    num_merges=user.num_merges
                )
                if user.num_deletes or user.num_merges
                else ''
            ),
            num=user.num_tracks,
            avglen=datetime.timedelta(seconds=user.avg_length / 1000)
        )
    )

def calc_integer_form(user_id, gmean):
    '''
    The calculated geometric mean is rounded to an integer value.
    '''

    logging.info(
        'Calculating the geometric mean of the track lengths for the user.'
    )
    with decimal.localcontext() as ctx:
        ctx.prec = 64
        avg_length = int(gmean.to_integral_value())

    logging.info(
        'Integer Geometric mean is: {gmean} milliseconds.'.format(gmean=avg_length)
    )

    deferred.defer(finalize_user, user_id, avg_length, _queue='lib-upd')

def calc_geomean(user_id, length_product, power):
    '''
    Calculates the geometric mean from the values passed to it. Because the
    length_product can be a very large number, this must use the decimal
    library, which is very slow.
    '''

    logging.info(
        'Calculating the geometric mean of the track lengths for the user.'
    )
    with decimal.localcontext() as ctx:
        ctx.prec = 64
        gmean = ctx.power(long(length_product), power)

    logging.info(
        'Real Geometric mean is: {gmean} milliseconds.'.format(gmean=gmean)
    )

    deferred.defer(calc_integer_form, user_id, gmean, _queue='lib-upd')


def calc_power(user_id, length_product, num_tracks):
    '''
    Calculates the power to use for the gemetric mean, which is the inverse of
    the number of tracks that is given.
    '''

    logging.info(
        'Calculating the geometric mean of the track lengths for the user.'
    )
    with decimal.localcontext() as ctx:
        ctx.prec = 64
        power = ctx.divide(1, int(num_tracks))

    logging.info(
        'Power is: {power}'.format(power=power)
    )

    deferred.defer(calc_geomean, user_id, length_product, power, _queue='lib-upd')


def calc_length_product(user_id, batch_num):
    '''
    Calculates the product of all of the track lengths in the library.
    This can make a very, very big number.
    '''

    user = ndb.Key(urlsafe=user_id).get()
    logging.info('Calculating the product of the track lengths for the user.'.format(
        uid=user.key.id()
    ))

    if len(user.updated_batches) < batch_num:
        logging.info('Not completed with updating... rescheduling calculation.')
        logging.debug(
            'Batches: {num_batches} (processed) < {batch_num} (total)'.format(
                num_batches=len(user.updated_batches),
                batch_num=batch_num
            )
        )
        deferred.defer(calc_length_product, user_id, batch_num, _queue='lib-upd')
        return

    else:
        logging.debug('{batch_num} total batches processed, for a total of {num} tracks.'.format(
            batch_num=batch_num,
            num=user.num_tracks,
        ))

    length_product = str(reduce(operator.mul, map(long, user.update_lengths), 1))

    logging.info('Product of {num} track lengths is: {len_prod}'.format(
        num=user.num_tracks,
        len_prod=length_product
    ))

    deferred.defer(calc_geomean, user_id, length_product, user.num_tracks, _queue='lib-upd')


@ndb.transactional
def count_updater(user_id, num, len_prod_piece, myhash, batch_num, num_deletes=0, num_merges=0):
    '''
    Updates one batch worth of track statistics.
    '''
    user = ndb.Key(urlsafe=user_id).get()

    if myhash not in user.updated_batches:
        user.num_tracks += num
        user.update_lengths.append(len_prod_piece)
        user.updated_batches.append(myhash)
        user.num_deletes += num_deletes
        user.num_merges += num_merges
        user.put()

        return True

    else:
        return False


def update_num_tracks(user_id, num, len_prod_piece, myhash, final, batch_num, num_deletes, num_merges):
    '''
    Wrapper to update one batch worth of track statistics.
    '''

    updated = count_updater(user_id, num, len_prod_piece, myhash, batch_num, num_deletes, num_merges)

    if updated:
        logging.info('[Batch #{batch_num}] User counts updated'.format(
            batch_num=batch_num
        ))

        if final:
            logging.info(
                '[Batch #{batch_num}] Scheduling finalizer task...'.format(
                    batch_num=batch_num
                )
            )
            deferred.defer(calc_length_product, user_id, batch_num, _queue='lib-upd')

    else:
        logging.info('[Batch #{batch_num}] Already updated, skipping.'.format(
            batch_num=batch_num
        ))


def make_entity(parent_key, track, batch_num):
    '''
    Converts data from gmusicapi into a models.Track entity.
    '''
    entity = models.Track(
        parent=parent_key,
        id=track['id'],
        title=track['title'],
        created=to_datetime(track['creationTimestamp']),
        recent=to_datetime(track['recentTimestamp']),
        modified=to_datetime(track['lastModifiedTimestamp']),
        play_count=int(track.get('playCount', 0)),
        duration_millis=int(track['durationMillis']),
        rating=int(track.get('rating', 0)),
        artist=track['artist'],
        album=track['album'],
        rand_num=int(random.randrange(2**32)),
    )

    with lib.suppress(KeyError, IndexError):
        entity.artist_art = track['artistArtRef'][0]['url']

    with lib.suppress(KeyError, IndexError):
        entity.album_art = track['albumArtRef'][0]['url']

    with lib.suppress(KeyError):
        entity.disc_number = int(track['discNumber'])

    with lib.suppress(KeyError):
        entity.total_disc_count = int(track['totalDiscCount'])

    with lib.suppress(KeyError):
        entity.track_number = int(track['trackNumber'])

    with lib.suppress(KeyError):
        entity.total_track_count = int(track['totalTrackCount'])

    with lib.suppress(KeyError):
        entity.album_artist = track['albumArtist']

    with lib.suppress(KeyError):
        entity.year = int(track['year'])

    with lib.suppress(KeyError):
        entity.composer = track['composer']

    with lib.suppress(KeyError):
        entity.genre = track['genre']

    with lib.suppress(KeyError):
        entity.comment = track['comment']

    logging.debug('[Batch #{batch_num}] Entry:\n{data}'.format(
        batch_num=batch_num,
        data=entity
    ))

    return entity


def load_batch(user_id, last_update, chunk, final, batch_num):
    '''
    Loads a batch of tracks into models.Track entities. This is used to do daily
    maintenence on the library, only updating what has changed, skipping
    unchanged tracks.
    '''
    logging.info(
        '[Batch #{batch_num}] Processing chunk: {chunk} tracks.'.format(
            chunk=len(chunk),
            batch_num=batch_num,
        )
    )

    parent_key = ndb.Key(urlsafe=user_id)  # Library tracks tied to a user.

    myhash = base64.urlsafe_b64encode(
        hashlib.md5(
            '::'.join(
                track['id']
                for track in chunk
            )
        ).digest()
    )

    try:
        # Place keys into buckets
        deletes, merge_ids = zip(*tuple(
            (
                ndb.Key(flat=[models.Track, track['id']], parent=parent_key)
                if track['deleted']
                else None,

                track['id']
                if not track['deleted']
                else None,
            )
            for track in chunk
            if to_datetime(track['lastModifiedTimestamp']) >= last_update
        ))

        # Clean up buckets
        deletes = tuple(key for key in deletes if key is not None)
        merge_ids = tuple(key for key in merge_ids if key is not None)
        
        num_deletes = len(deletes)
        num_merges = len(merge_ids)
        
        futures = []

        if merge_ids:
            merges = tuple(
                make_entity(parent_key, track, batch_num)
                for track in chunk
                if track['id'] in merge_ids
            )
    
            logging.info(
                ' '.join((
                    '[Batch #{batch_num}] Updating {num}',
                    'tracks in datastore.'
                )).format(
                    batch_num=batch_num,
                    num=num_merges
                )
            )
    
            futures.extend(ndb.put_multi_async(merges))
    
        if deletes:
            logging.info(
                ' '.join((
                    '[Batch #{batch_num}] Deleting {num}',
                    'tracks from datastore.'
                )).format(
                    batch_num=batch_num,
                    num=num_deletes
                )
            )
            futures.extend(ndb.delete_multi_async(deletes))
    
        if futures:
            ndb.Future.wait_all(futures)

    except ValueError:
        deletes = merge_ids = ()
        num_deletes = num_merges = 0

    num_tracks = len(chunk) - len(deletes)

    all_lens = tuple(
        int(track['durationMillis'])
        for track in chunk
        if not track['deleted']
    )
    length_product = str(reduce(operator.mul, all_lens, 1))

    last_tracks = final is not None

    deferred.defer(
        update_num_tracks,
        user_id,
        num_tracks,
        length_product,
        myhash,
        last_tracks,
        batch_num,
        num_deletes,
        num_merges,
        _queue='lib-upd'
    )

    logging.info(
        ' '.join((
            '[Batch #{batch_num}] Completed: {count} processed;',
            '{updcount} merged; {delcount} deleted'
        )).format(
            batch_num=batch_num,
            count=num_tracks,
            updcount=num_merges,
            delcount=num_deletes
        )
    )
    
    if final is not None:
        logging.info('[Batch #{batch_num}] All batches updated.'.format(
            batch_num=batch_num
        ))


def initialize_batch(user_id, last_update, chunk, final, batch_num):
    '''
    Loads a batch of tracks into models.Track entities. This is used to
    initialize the library (first run).
    '''
    logging.info(
        '[Batch #{batch_num}] Initializing chunk: {chunk} tracks'.format(
            chunk=len(chunk),
            batch_num=batch_num,
        )
    )
    
    parent_key = ndb.Key(urlsafe=user_id)  # Library tracks tied to a user.

    myhash = base64.urlsafe_b64encode(
        hashlib.md5(
            '::'.join(
                track['id']
                for track in chunk
            )
        ).digest()
    )
    
    # Set up keys, and figure out tests for placing into buckets.
    batch = tuple(
        make_entity(parent_key, track, batch_num)
        for track in chunk
        if not track['deleted']
    )

    if batch:
        logging.info(
            '[Batch #{batch_num}] Putting {num} tracks into datastore.'.format(
                batch_num=batch_num, num=len(batch)
            )
        )
        
        futures = ndb.put_multi_async(batch)
        
        ndb.Future.wait_all(futures)
        
    num_tracks = len(batch)
    all_lens = tuple(
        int(track['durationMillis'])
        for track in chunk
        if not track['deleted']
    )
    length_product = str(reduce(operator.mul, all_lens, 1))
    last_tracks = final is not None
    deferred.defer(
        update_num_tracks,
        user_id,
        num_tracks,
        length_product,
        myhash,
        last_tracks,
        batch_num,
        _queue='lib-upd'
    )

    logging.info(
        '[Batch #{batch_num}] Completed: {num_tracks} tracks added.'.format(
            batch_num=batch_num,
            num_tracks=len(batch),
        )
    )

    if final is not None:
        logging.info('[Batch #{batch_num}] All batches initialized.'.format(
            batch_num=batch_num
        ))


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
    last_update,
    initial,
    encrypted_passwd,
    _token=None,
    _num=0,
    _num_tracks=0
):
    '''
    Retrieves a batch of tracks from Google Play Music, to be processed.
    '''
    logging.info('Starting get_batch()')
    chunk_size = 100
    num_batches = 20

    start = _num + 1
    stop = start + num_batches

    with musicapi_connector(user_id, encrypted_passwd) as api:
        for batch_num in xrange(start, stop):
            logging.info(
                ' '.join((
                    '[Batch #{batch_num}] Retrieving batch',
                    'from Google Play Music'
                )).format(
                    batch_num=batch_num
                )
            )
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
                    '[Batch #{batch_num}] Retrieved {chunk_size} tracks,',
                    'queued for processing.'
                )).format(
                    batch_num=batch_num,
                    chunk_size=_num_tracks
                )
            )
            deferred.defer(
                initialize_batch if initial else load_batch,
                user_id,
                last_update,
                results,
                final_track_count,
                batch_num,
                _queue='lib-upd'
            )
            if _token is None:
                break

    if _token is not None:
        uid = ndb.Key(urlsafe=user_id).id()
        logging.info(
            '[Batch #{batch_num}] Preparing to retrieve more batches for user {uid}...'.format(
                batch_num=batch_num,
                uid=uid
            )
        )
        deferred.defer(
            get_batch,
            user_id,
            last_update,
            initial,
            crypt.encrypt(crypt.decrypt(encrypted_passwd, uid), uid),
            _token=_token,
            _num=batch_num,
            _num_tracks=_num_tracks,
            _queue='lib-upd'
        )

    else:
        logging.info('[Batch #{batch_num}] All batches retrieved.'.format(batch_num=batch_num))
