from google.appengine.ext import ndb

# Create your models here.
# Note, using Google App Engine NDB models here, rather than django ones.


class User(ndb.Model):
    password = ndb.StringProperty()
    email = ndb.StringProperty(required=True)
    updating = ndb.BooleanProperty(required=True, default=False)
    update_start = ndb.DateTimeProperty()
    update_stop = ndb.DateTimeProperty()
    num_tracks = ndb.IntegerProperty()


class Track(ndb.Model):
    user = ndb.StringProperty(required=True)
    touched = ndb.DateTimeProperty(required=True)  # For finding/removing deleted tracks.
    title = ndb.StringProperty(required=True)  # For searchability
    disc_number = ndb.IntegerProperty()  # for display/sorting purposes
    total_disc_count = ndb.IntegerProperty()  # for display/sorting purposes
    track_number = ndb.IntegerProperty()  # for display/sorting purposes
    total_track_count = ndb.IntegerProperty()  # for display/sorting purposes
    artist = ndb.StringProperty()  # for display/sorting purposes, name of the artist
    artist_art = ndb.StringProperty(indexed=False)  # for display purposes, url to artist art
    album_artist = ndb.StringProperty()  # name of the artist
    album = ndb.StringProperty()  # for display/sorting purposes, name of the album
    album_art = ndb.StringProperty(indexed=False) # for display purposes, url to album art
    year = ndb.IntegerProperty()  # For searchability
    composer = ndb.StringProperty(required=True, default='')  # For searchability
    genre = ndb.StringProperty(required=True, default='')  # For searchability
    created = ndb.DateTimeProperty(required=True)  # Used in LRA calculation
    modified = ndb.DateTimeProperty(required=True)  # Used in LRP calculation
    play_count = ndb.IntegerProperty(required=True, default=0)  # Used in LRA, LRP, LOP calculations
    duration_millis = ndb.IntegerProperty(indexed=False, required=True)  # Used to help determine the number of tracks to play
    rating = ndb.IntegerProperty(required=True, default=0, choices=(0, 1, 2, 3, 4, 5))  # Used in subgroup processing
    comment = ndb.StringProperty(indexed=False, default='')  # Used for possibly figuring out rating, partition, and holidays


class Partition(ndb.Model):
    name = ndb.StringProperty(required=True)


class DateRange(ndb.Model):
    start = ndb.DateProperty(required=True)
    end = ndb.DateProperty(required=True)


class Holiday(ndb.Model):
    name = ndb.StringProperty(required=True)
    ranges = ndb.StructuredProperty(DateRange, repeated=True)

    
class TrackLists(ndb.Model):
    user = ndb.StringProperty(required=True)
    touched = ndb.DateTimeProperty(required=True)
    partition = ndb.StringProperty()  # My field! Referemces Partition model id
    holidays = ndb.StringProperty(repeated=True)  # My field! References Holiday model id
