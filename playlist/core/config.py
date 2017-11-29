"""
Configuration settings that are used throughout gpm-playlist.

The primary purpose of this module is to provide easy programmatic access to
various YAML files used in gpm-playlist. These files are to be used as either
synchronous or asynchronous context managers (using the `with` or `async with`
commands). Generally, use as an asynchronous context manager always in an
asynchronous context, this will avoid blocking issues when opening the file.

Config objects function in many ways like a read-only dictionary structure,
where lists are automatically converted to tuples, and sets are automatically
converted to frozensets. This is done through the :py:func:`to_config`
function.  The objects also use the copy protocol, and can be converted into
dictionaries with lists and sets (as appropriate) by using
:py:func:`copy.deepcopy`. Config object data can be accessed like dictionary
keys (ie: `config['settings']) or as object attributes (ie: `config.settings`).
"""
import sys

from playlist.core.yaml import _config
config = _config.RootConfig()
type(config).__doc__ = __doc__
sys.modules[__name__] = config
