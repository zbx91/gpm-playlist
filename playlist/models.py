from Crypto.Random import random

from google.appengine.ext import ndb

# Create your models here.
# Note, using Google App Engine NDB models here, rather than django ones.


class User(ndb.Model):
    password = ndb.StringProperty(indexed=False, required=True)
    email = ndb.StringProperty(indexed=False, required=True)
    updating = ndb.BooleanProperty(indexed=False, required=True, default=False)
    last_update_start = ndb.DateTimeProperty(indexed=False)
    update_start = ndb.DateTimeProperty(indexed=False)
    update_stop = ndb.DateTimeProperty(indexed=False)
    updated_batches = ndb.StringProperty(repeated=True, indexed=False)
    num_tracks = ndb.IntegerProperty(indexed=False, default=0)
    usable_num_tracks = ndb.IntegerProperty(indexed=False, default=0)
    avg_length = ndb.IntegerProperty(indexed=False, default=0)
    update_lengths = ndb.StringProperty(indexed=False, repeated=True)
    num_merges = ndb.IntegerProperty(indexed=False, default=0)
    num_deletes = ndb.IntegerProperty(indexed=False, default=0)
    skip_ratings = ndb.IntegerProperty(indexed=False, repeated=True)

class Partition(ndb.Model):
    name = ndb.StringProperty(required=True)


class DateRange(ndb.Model):
    start = ndb.DateProperty(required=True)
    end = ndb.DateProperty(required=True)


class Holiday(ndb.Model):
    name = ndb.StringProperty(required=True)
    ranges = ndb.StructuredProperty(DateRange, repeated=True)


class Track(ndb.Model):
    title = ndb.StringProperty(required=True)  # For searchability
    disc_number = ndb.IntegerProperty()  # for display/sorting purposes
    total_disc_count = ndb.IntegerProperty()  # for display/sorting purposes
    track_number = ndb.IntegerProperty()  # for display/sorting purposes
    total_track_count = ndb.IntegerProperty()  # for display/sorting purposes
    artist = ndb.StringProperty()  # for display/sorting purposes, name of the artist
    artist_art = ndb.StringProperty()  # for display purposes, url to artist art
    album_artist = ndb.StringProperty()  # name of the artist
    album = ndb.StringProperty()  # for display/sorting purposes, name of the album
    album_art = ndb.StringProperty() # for display purposes, url to album art
    year = ndb.IntegerProperty()  # For searchability
    composer = ndb.StringProperty(required=True, default='')  # For searchability
    genre = ndb.StringProperty(required=True, default='')  # For searchability
    created = ndb.DateTimeProperty(required=True)  # Used in LRA calculation
    modified = ndb.DateTimeProperty(required=True)  # Used in LRP calculation
    play_count = ndb.IntegerProperty(required=True, default=0)  # Used in LRA, LRP, LOP calculations
    duration_millis = ndb.IntegerProperty(required=True)  # Used to help determine the number of tracks to play
    rating = ndb.IntegerProperty(required=True, default=0, choices=(0, 1, 2, 3, 4, 5))  # Used in subgroup processing
    comment = ndb.StringProperty(default='')  # Used for possibly figuring out rating, partition, and holidays
    partition = ndb.StringProperty()  # My field! Referemces Partition model id
    holidays = ndb.StringProperty(repeated=True)  # My field! References Holiday model id
    rand_num = ndb.ComputedProperty(lambda s: int(random.randrange(2**32)))  # My field! For use with random selections of tracks