from google.appengine.api import users
from google.appengine.ext import ndb

from django.http import HttpResponse
from django.shortcuts import render

from core import crypt

import os
google_path = os.path.join(os.path.split(os.path.dirname(__file__))[0], 'sitepackages', 'google')
import google
google.__path__.append(google_path)

import gmusicapi

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