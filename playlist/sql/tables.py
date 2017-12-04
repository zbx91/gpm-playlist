"""
Dynamically creates table definitions on an as-needed basis for SQLAlchemy.

This class eliminates mass redundency in SQLAlchemy table definition
implementations. All tables are now defined in YAML files that get loaded
here. Further, the remote oracle database connections will automatically
generate a table definition when it is used, which then becomes available for
subsequent uses.

*****
Usage
*****

This is intended to be used as follows::

    from playlist.sql import tables

**********
Module API
**********

See Also:
    :py:class:`playlist.sql._tables.MainTablesConfig`

"""

import sys

from . import _tables


# Being very sneaky here. The playlist.sql.tables module is actually an object.
tables = _tables.MainTablesConfig()
type(tables).__doc__ = __doc__
sys.modules[__name__] = tables
