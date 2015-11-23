#!/usr/bin/env python
import os
import sys

import google
google_path = os.path.join(
    os.path.split(os.path.dirname(__file__))[0],
    'sitepackages',
    'google_appengine',
    'google'
)
google.__path__.append(google_path)
from playlist.boot import fix_path
fix_path()

if __name__ == "__main__":
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "playlist.settings")

    from djangae.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)
