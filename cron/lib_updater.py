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


def make_entity(parent_key, track):
    entity = models.Track(
        parent=parent_key,
        id=track['id'],
        title=track['title'],
        created=datetime.datetime.utcfromtimestamp(
            int(track['creationTimestamp']) / 1000000
        ),
        recent=datetime.datetime.utcfromtimestamp(
            int(track['recentTimestamp']) / 1000000
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

    logging.debug('Entry:\n{data}'.format(data=entity))

    return entity


@ndb.transactional
def finalize_user(user_id, batch_num):
    user = ndb.Key(urlsafe=user_id).get()
    if len(user.updated_batches) < batch_num:
        logging.info('Not completed with updating... rescheduling finalizer.')
        logging.debug('{num_batches} < {batch_num}'.format(num_batches=len(user.updated_batches), batch_num=batch_num))
        deferred.defer(finalize_user, user_id, batch_num)
        return

    del user.updated_batches
    length_product = reduce(operator.mul, map(long, user.update_lengths), 1)
    with decimal.localcontext() as ctx:
        ctx.prec = 64
        power = ctx.divide(1, int(user.num_tracks))
        user.avg_length = int(
            ctx.power(length_product, power).to_integral_value()
        )
    del user.update_lengths
    user.updating = False
    user.update_stop = datetime.datetime.now()
    user.put()
    logging.info(
        ' '.join((
            'Library updated, {num} tracks total,',
            'average length of {avglen}'
        )).format(
            num=user.num_tracks,
            avglen=datetime.timedelta(seconds=user.avg_length / 1000)
        )
    )

@ndb.transactional
def update_num_tracks(user_id, num, len_prod_piece, myhash, final, batch_num):
    logging.info(
        ' '.join((
            'Updating track count with {num} tracks, length product =',
            '{len_prod}, Final = {final}'
        )).format(
            num=num,
            final=final,
            len_prod=len_prod_piece
        )
    )
    user = ndb.Key(urlsafe=user_id).get()
    if myhash not in user.updated_batches:
        user.num_tracks += num
        user.update_lengths.append(len_prod_piece)
        user.updated_batches.append(myhash)
        user.put()

        if final:
            deferred.defer(
                finalize_user,
                user_id,
                batch_num,
                _queue='lib-upd'
            )


def load_batch(user_id, start, initial, chunk, final, batch_num):
    '''
    Loads a batch of tracks into models.Track entities.
    '''
    logging.info('Processing chunk: {chunk} tracks'.format(chunk=len(chunk)))
    batch = []
    futures = []

    parent_key = ndb.Key(urlsafe=user_id)  # Library tracks tied to a user.

    # Set up keys, and figure out tests for placing into buckets.
    key_gen = (
        (
            ndb.Key(flat=[models.Track, track['id']], parent=parent_key),
            track['deleted'],
            int(track['lastModifiedTimestamp']) >= start
        )
        for track in chunk
    )

    with lib.suppress(ValueError):
        # Place keys into buckets
        deletes, batch_ids, check_ids = zip(*tuple(
            (
                key if deleted else None,
                key if not deleted and modified else None,
                key if initial and not (deleted or modified) else None,
            )
            for key, deleted, modified in key_gen
        ))

        # Clean up buckets
        deletes = tuple(key for key in deletes if key is not None)
        batch_ids = tuple(key for key in batch_ids if key is not None)
        check_ids = tuple(key for key in check_ids if key is not None)

        if check_ids:
            existing_ids = set(
                item.key.id()
                for item in ndb.get_multi(check_ids)
            )
            check_ids = set(item.id() for item in check_ids)
            new_ids = tuple(check_ids - existing_ids)
            del existing_ids
            check_ids = (
                ndb.Key(flat=[models.Track, track_id], parent=parent_key)
                for track_id in new_ids
            )
            del new_ids
            batch_ids = itertools.chain(batch_ids, check_ids)

        batch_track_gen = (track for track in chunk if track['id'] in batch_ids)
        batch = tuple(
            make_entity(parent_key, track)
            for track in batch_track_gen
        )

        logging.info(
            'Putting {num} tracks into datastore.'.format(
                num=len(batch)
            )
        )
        futures.extend(ndb.put_multi_async(batch))

        if deletes:
            logging.info(
                'Deleting {num} tracks from datastore.'.format(
                    num=len(deletes)
                )
            )
            futures.extend(ndb.delete_multi_async(deletes))

        ndb.Future.wait_all(futures)
        logging.info(
            ' '.join((
                'Completed batch: {count} tracks updated,',
                '{delcount} deleted.'
            )).format(
                count=len(batch),
                delcount=len(deletes)
            )
        )

        myhash = base64.urlsafe_b64encode(
            hashlib.md5(
                '::'.join(
                    track['id']
                    for track in chunk
                )
            ).digest()
        )
        num_tracks = len(chunk) - len(deletes)
        all_lens = tuple(
            int(track['durationMillis'])
            for track in chunk
            if not track['deleted']
        )
        length_product = str(reduce(operator.mul, all_lens, 1))
        logging.info('Track lengths: {lens}'.format(lens=all_lens))
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

    if final is not None:
        logging.info('All batches completed.')


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
    initial,
    encrypted_passwd,
    _token=None,
    _num=0,
    _num_tracks=0
):
    '''
    Retrieves a batch of tracks from Google Play Music, to be processed.
    '''
    logging.info('Getting batch #{num}'.format(num=_num))
    chunk_size = 100
    num_batches = 20

    start = _num + 1
    stop = start + num_batches

    with musicapi_connector(user_id, encrypted_passwd) as api:
        for count in xrange(start, stop):
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
                    'Batch #{count} loaded, {chunk_size} tracks',
                    'queued for processing, {num_tracks} tracks total.'
                )).format(
                    count=count,
                    chunk_size=len(results),
                    num_tracks=_num_tracks
                )
            )
            deferred.defer(
                load_batch,
                user_id,
                start,
                initial,
                results,
                final_track_count,
                count,
                _queue='lib-upd'
            )
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
            initial,
            crypt.encrypt(crypt.decrypt(encrypted_passwd, uid), uid),
            _token=_token,
            _num=count,
            _num_tracks=_num_tracks,
            _queue='lib-upd'
        )
