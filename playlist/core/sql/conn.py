"""
Contains the connector objects used for all database actions.

*****
Usage
*****

If needed, it should be used through::

    from playlist.core.sql import conn

**********
Module API
**********

See Also:
    :py:class:`playlist.core.sql._conn.MainConnectionConfig`

"""
import sys

from . import _conn


# Being very sneaky here. The playlist.core.sql.conn module is an object.
conn = _conn.MainConnectionConfig()
type(conn).__doc__ = __doc__
sys.modules[__name__] = conn
