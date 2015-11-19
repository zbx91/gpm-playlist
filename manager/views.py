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
        user_id = user.key.id()
        deferred.defer(
            lib_updater.get_batch,
            user_id,
            start,
            crypt.encrypt(crypt.decrypt(user.password, user_id), user_id)
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