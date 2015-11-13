from google.appengine.ext import ndb

# Create your models here.
# Note, using Google App Engine NDB models here, rather than django ones.

class Artist(ndb.Model):
    name = ndb.StringProperty(required=True)
    art = ndb.StringProperty(indexed=False, required=False)


class Album(ndb.Model):
    name = ndb.StringProperty(required=True)
    art = ndb.StringProperty(indexed=False, required=False)


class Partition(ndb.Model):
    name = ndb.StringProperty(required=True)


class DateRange(ndb.Model):
    start = ndb.DateProperty(required=True)
    end = ndb.DateProperty(required=True)


class Holiday(ndb.Model):
    name = ndb.StringProperty(required=True)
    ranges = ndb.StructuredProperty(DateRange, repeated=True)


class User(ndb.Model):
    password = ndb.StringProperty(required=False)

class Track(ndb.Model):
    title = ndb.StringProperty(required=True)  # For searchability
    disc_number = ndb.IntegerProperty(required=False)  # for display/sorting purposes
    total_disc_count = ndb.IntegerProperty(required=False)  # for display/sorting purposes
    track_number = ndb.IntegerProperty(required=False)  # for display/sorting purposes
    total_track_count = ndb.IntegerProperty(required=False)  # for display/sorting purposes
    artist = ndb.StringProperty(required=False)  # References Artist model id, for searchability
    album_artist = ndb.StringProperty(required=False)  # Not a reference
    album = ndb.StringProperty(required=False)  # References Album model id, for searchability
    year = ndb.IntegerProperty(required=False)  # For searchability
    composer = ndb.StringProperty(required=True, default='')  # For searchability
    genre = ndb.StringProperty(required=True, default='')  # For searchability
    created = ndb.DateTimeProperty(required=True)  # Used in LRA calculation
    modified = ndb.DateTimeProperty(required=True)  # Used in LRP calculation
    play_count = ndb.IntegerProperty(required=True, default=0)  # Used in LRA, LRP, LOP calculations
    duration_millis = ndb.IntegerProperty(indexed=False, required=True)  # Used to help determine the number of tracks to play
    rating = ndb.IntegerProperty(required=True, default=0, choices=(0, 1, 2, 3, 4, 5))  # Used in subgroup processing
    comment = ndb.StringProperty(indexed=False, required=False, default='')  # Used for possibly figuring out rating, partition, and holidays
    partition = ndb.StringProperty(required=False)  # My field! Referemces Partition model id
    holidays = ndb.StringProperty(required=False, repeated=True)  # My field! References Holiday model id