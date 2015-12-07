import calendar
import datetime
import itertools
import json
import logging
import operator
import pprint
import time
import urllib

from google.appengine.api import users
from google.appengine.ext import deferred
from google.appengine.ext import ndb

from django.http import HttpResponse
from django.shortcuts import render

import requests

from core import crypt, lib
from playlist import models


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


def erase_tracks(user_id):
    batch_size = 750
    logging.info(
        'Attempting to erase {size} tracks from library...'.format(
            size=batch_size
        )
    )
    parent_key = ndb.Key(urlsafe=user_id)
    keys = models.Track.query(ancestor=parent_key).fetch(
        batch_size,
        keys_only=True
    )
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
        ' '.join((
            '<html><body><p>Starting to erase library',
            'for user {user}</p></body></html>'
        )).format(user=user.email())
    )


def get_tracks(request):
    user = users.get_current_user()
    if user is None:
        return HttpResponse('Not logged in.')

    cursor = ndb.Cursor(urlsafe=request.GET.get('next_page', None))
    batch_size = int(request.GET.get('batch_size', 100))

    # Set up filters

    filter_param_gen = (
        filter_param.split(',')
        for filter_param in request.GET.getlist('filter', [])
    )

    filter_name_split_gen = (
        (
            param[0],
            iter(param[1:])
        )
        for param in filter_param_gen
    )

    filter_oper_parse_gen = (
        (
            getattr(models.Track, name),
            (
                (
                    constraint[:2],
                    constraint[2:],
                ) if constraint[:2] in ('>=', '<=', '!=')
                else (
                    constraint[:1],
                    constraint[1:],
                ) if constraint[:1] in ('=', '<', '>')
                else (constraint, )
                for constraint in constraints
            )
        )
        for name, constraints in filter_name_split_gen
    )

    filter_oper_split_gen = (
        (field, ) + tuple(
            zip(
                *tuple(
                    (
                        constraint if len(constraint) == 2 else None,
                        constraint if len(constraint) == 1 else None,
                    )
                    for constraint in constraints
                )
            )
        )
        for field, constraints in filter_oper_parse_gen
    )

    filter_oper_condense_gen = (
        (
            field,
            tuple(constr for constr in oper_constr if constr is not None),
            tuple(constr for constrs in in_constr if constrs is not None for constr in constrs if constr is not None),
        )
        for field, oper_constr, in_constr in filter_oper_split_gen
    )

    def conv_value(field, value):
        logging.debug((field, value))
        if value == 'None':
            return None

        elif field._name == 'rand_num':
            return int(value)

        elif isinstance(field, ndb.IntegerProperty):
            return int(value)

        elif isinstance(field, ndb.DateTimeProperty):
            return datetime.datetime.strptime(value, '%Y-%m-%d %H:%M:%S')

        else:
            return value

    filter_oper_convert_gen = (
        itertools.chain(
            (
                (
                    (
                        operator.ne if oper == '!='
                        else operator.gt if oper == '>'
                        else operator.ge if oper == '>='
                        else operator.lt if oper == '<'
                        else operator.le if oper == '<='
                        else operator.eq
                    )(field, conv_value(field, value))
                    for oper, value in oper_constr
                ) if oper_constr else (None, )
            ), (
                field.IN(tuple(conv_value(field, value) for value in in_constr))
                if len(in_constr) > 1
                else operator.eq(field, conv_value(field, in_constr[0]))
                if len(in_constr) == 1
                else None,
            )
        )
        for field, oper_constr, in_constr in filter_oper_condense_gen
    )

    filters = tuple(
        constr
        for constrs in filter_oper_convert_gen
        for constr in constrs
        if constr is not None
    )

    # Set up sorting

    sort_gen = (
        -getattr(models.Track, param[1:])
        if param[0] == '-' else
        getattr(models.Track, param)
        for param in itertools.chain(request.GET.getlist('sort', []), ('key', ))
    )

    user_id = ndb.Key(models.User, user.user_id())

    query_args = ()
    query_kwargs = {'ancestor': user_id}

    if len(filters) == 1:
        query_args += (filters[0], )

    elif len(filters) > 1:
        query_args += (ndb.AND(*filters), )

    query = models.Track.query(*query_args, **query_kwargs)

    for sorter in sort_gen:
        query = query.order(sorter)

    track_batch, next_cursor, more = query.fetch_page(
        batch_size,
        start_cursor=cursor
    )

    return HttpResponse(
        json.dumps({
            'next_page': next_cursor.urlsafe() if next_cursor is not None and more else None,
            'batch_size': batch_size,
            'tracks': tuple(
                {
                    'id': track.key.id(),
                    'title': track.title,
                    'disc_number': track.disc_number,
                    'total_disc_count': track.total_disc_count,
                    'track_number': track.track_number,
                    'total_track_count': track.total_track_count,
                    'artist': track.artist,
                    'artist_art': track.artist_art,
                    'album_artist': track.album_artist,
                    'album': track.album,
                    'album_art': track.album_art,
                    'year': track.year,
                    'composer': track.composer,
                    'genre': track.genre,
                    'created': int(
                        calendar.timegm(
                            track.created.timetuple()
                        ) * 1000 + track.created.microsecond / 1000
                    ),
                    'modified': int(
                        calendar.timegm(
                            track.modified.timetuple()
                        ) * 1000 + track.modified.microsecond / 1000
                    ),
                    'play_count': track.play_count,
                    'duration_millis': track.duration_millis,
                    'rating': track.rating,
                    'comment': track.comment,
                    'partition': track.partition,
                    'holidays': tuple(holiday for holiday in track.holidays),
                }
                for track in track_batch
            ),
        }),
        content_type='text/json'
    )
    
    
def get_albums(request):
    user = users.get_current_user()
    user_id = ndb.Key(models.User, user.user_id())
    
    query = models.Track.query(
        projection=[
            'album',
            'album_artist',
            'album_art',
            'total_disc_count',
            'year',
            'duration_millis',
            'rating',
            'partitions',
            'holidays',
        ],
        ancestor=user_id
    )

    results = query.fetch()

    return HttpResponse(
        json.dumps({
            'albums': tuple(
                {
                    'album': album.album,
                    'album_artist': album.album_artist,
                    'album_art': album.album_art,
                    'total_disc_count': album.total_disc_count,
                    'year': album.year,
                    'duration_millis': album.duration_millis,
                    'rating': album.rating,
                    'partitions': album.partition,
                    'holidays': tuple(holiday for holiday in album.holidays),
                }
                for album in results
            ),
        }),
        content_type='text/json'
    )