import datetime
import functools

from django.http import HttpResponse
from django.shortcuts import render

from google.appengine.ext import deferred
from google.appengine.ext import ndb

from playlist import models
from core import crypt

from . import lib_updater

# Create your views here.

def autoload_libraries(request):  # Cron Job.
    updates = []
    defer_list = []
    for user in models.User.query():
        if user.updating:
            continue
        
        user.updating = True
        user.num_tracks = 0
        del user.updated_batches
        del user.update_lengths
        del user.avg_length
        
        try:
            start = (
                user.update_start - datetime.datetime(1970,1,1)
            ).total_seconds() * 1000000
            
        except TypeError:
            start = 0
            
        user.update_start = datetime.datetime.now()
        
        del user.update_stop
        updates.append(user)
        user_id = user.key.urlsafe()
        uid = user.key.id()
        defer_list.append(
            (
                user_id,
                start,
                crypt.encrypt(crypt.decrypt(user.password, uid), uid)
            )
        )

    if updates:
        futures = ndb.put_multi_async(updates)
        ndb.Future.wait_all(futures)
        
    if defer_list:
        defer_batch = functools.partial(deferred.defer, lib_updater.get_batch, _queue='lib-upd')
        func_defer = lambda a: defer_batch(*a)
        tuple(map(func_defer, defer_list))

    return HttpResponse(
        ' '.join((
            '<html><body><p>Starting music loading process',
            'for {num} user(s)...</p></body></html>'
        )).format(
            num=len(updates)
        ),
        status=202
    )
    
