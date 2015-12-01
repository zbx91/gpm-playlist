import datetime
import functools
import logging

from django.http import HttpResponse
from django.shortcuts import render

from google.appengine.ext import deferred
from google.appengine.ext import ndb

from playlist import models
from core import crypt, lib

from . import lib_updater

# Create your views here.

def autoload_libraries(request):  # Cron Job.
    updates = []
    futures = []
    for user in models.User.query():
        logging.info('Starting updating for user {uid}'.format(uid=user.key.id()))
        if user.updating:
            logging.warning('User {uid} already being updated!'.format(uid=user.key.id()))
            continue

        user.updating = True
        user.num_tracks = 0
        user.num_deletes = 0
        user.num_updates = 0
        del user.updated_batches
        del user.update_lengths
        del user.avg_length

        with lib.suppress(ValueError):
            if user.update_start and user.update_stop and user.update_stop > user.update_start:
                user.last_update_start = user.update_start

            elif not user.update_start:
                user.last_update_start = None

        initial = not user.last_update_start

        logging.debug(
            'Initial loading of library'
            if initial
            else 'Library last updated {last_start}'.format(
                last_start=user.last_update_start
            )
        )

        user.update_start = datetime.datetime.now()
        updates.append(user)
        user_id = user.key.urlsafe()
        uid = user.key.id()
        logging.info('Starting track processing for user {uid}'.format(uid=uid))
        deferred.defer(
            lib_updater.get_batch,
            user_id,
            user.last_update_start,
            initial,
            crypt.encrypt(crypt.decrypt(user.password, uid), uid)
        )
        futures.append(user.put_async())

    ndb.Future.wait_all(futures)

    logging.info('Done with update startup.')

    return HttpResponse(
        '<html><body><p>Music loading process started.</p></body></html>',
        status=202
    )

