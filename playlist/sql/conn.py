"""
Contains the connector objects used for all database actions.

*****
Usage
*****

If needed, it should be used through::

    from playlist.sql import conn

**********
Module API
**********

See Also:
    :py:class:`playlist.sql._conn.MainConnectionConfig`

"""
import sys

from playlist.sql import _conn


# Being very sneaky here. The playlist.sql.conn module is an object.
conn = _conn.MainConnectionConfig()
type(conn).__doc__ = __doc__
sys.modules[__name__] = conn
