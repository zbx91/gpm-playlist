import sys

from os.path import dirname, abspath, join, exists

from google.appengine.ext import ndb

PROJECT_DIR = dirname(dirname(abspath(__file__)))
SITEPACKAGES_DIR = join(PROJECT_DIR, "sitepackages")
APPENGINE_DIR = join(SITEPACKAGES_DIR, "google_appengine")

def fix_path():
    if exists(APPENGINE_DIR) and APPENGINE_DIR not in sys.path:
        sys.path.insert(1, APPENGINE_DIR)

    if SITEPACKAGES_DIR not in sys.path:
        sys.path.insert(1, SITEPACKAGES_DIR)


def get_app_config():
    """Returns the application configuration, creating it if necessary."""
    class Config(ndb.Model):
        secret_key = ndb.StringProperty()

    key = ndb.Key(Config, 'config')
    entity = key.get()
    if not entity:
        from django.utils.crypto import get_random_string
    
        # Create a random SECRET_KEY hash
        chars = 'abcdefghijklmnopqrstuvwxyz0123456789!@#$%^&*(-_=+)'
        secret_key = get_random_string(50, chars)

        entity = Config(key=key)
        entity.secret_key = str(secret_key)
        entity.put()
    return entity

def get_oauth2_creds():
    class Config(ndb.Model):
        client_secret = ndb.StringProperty()
        client_id = ndb.StringProperty()

    key = ndb.Key(Config, 'oauth2')
    entity = key.get()
    return entity