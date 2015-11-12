from django.db import models
from djangae import fields

# Create your models here.

class Track(models.Model):
    id_ = models.CharField(primary_key=True, editable=False)
    title = models.CharField()
    disc_number = models.IntegerField(blank=True, null=True)
    total_disc_count = models.IntegerField(blank=True, null=True)
    track_number = models.IntegerField(blank=True, null=True)
    total_track_count = models.IntegerField(blank=True, null=True)
    artist = models.CharField(blank=True, default='')
    album = models.CharField(blank=True, default='')
    album_artist = models.CharField(blank=True, default='')
    album_art = fields.ListField(fields.JSONField(), blank=True, null=True)
    artist_art = fields.ListField(fields.JSONField(), blank=True, null=True)
    year = models.IntegerField(blank=True, null=True)
    composer = models.CharField(blank=True, default='')
    genre = models.CharField(blank=True, default='')
    created = models.DateTimeField()
    modified = models.DateTimeField()
    play_count = models.IntegerField()
    duration_millis = models.IntegerField()
    rating = models.IntegerField(default=0)
    comment = models.CharField(blank=True, default='')
    partition = models.CharField(blank=True, default='') # My field!
    tags = fields.ListField(models.CharField(), blank=True, null=True) # My field!