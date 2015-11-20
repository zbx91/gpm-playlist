import datetime
import functools
import itertools
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

from core import crypt
from . import models, lib_updater


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


def autoload_libraries(request):  # Cron Job.
    updates = []
    for user in models.User.query():
        if user.updating:
            continue
        user.updating = True
        start = user.update_start = datetime.datetime.now()
        del user.update_stop
        updates.append(user)
        user_id = user.key.urlsafe()
        uid = user.key.id()
        deferred.defer(
            lib_updater.get_batch,
            user_id,
            start,
            crypt.encrypt(crypt.decrypt(user.password, uid), uid)
        )
    
    if updates:
        futures = ndb.put_multi_async(updates)
        ndb.Future.wait_all(futures)
        
    return HttpResponse(
        ' '.join((
            '<html><body><p>Starting music loading process',
            'for {num} user(s)...</p></body></html>'
        )).format(
            num=len(updates)
        ),
        status=202
    )
    
    
def erase_tracks(user_id):
    batch_size = 750
    logging.info(
        'Attempting to erase {size} tracks from library...'.format(
            size=batch_size
        )
    )
    parent_key = ndb.Key(urlsafe=user_id)
    keys = models.Track.query().ancestor(parent_key).fetch(batch_size, keys_only=True)
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
        '<html><body><p>Starting to erase library for user {user}</p></body></html>'.format(user=user.email())
    )