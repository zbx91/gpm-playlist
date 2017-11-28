"""
Enum and namedtuple instances used throughout gpm-playlist.

.. autosummary::
    :nosignatures:

    LogLevel

    BasePath
    FileExt
"""
import enum
import functools
import logging
import os
import pathlib

import appdirs


__all__ = (
    'ENCODING',

    # Logging level enum
    'LogLevel',

    # File/path enums
    'BasePath',
    'FileExt',
)

DIRS = appdirs.AppDirs('gpm-playlist', 'Cliff Hill')
ENCODING = 'utf-8'


class BasePath(enum.Enum):
    """The base paths to use for gpm-playlist."""

    SETTINGS = (
        pathlib.Path(DIRS.site_config_dir)
        if os.access(DIRS.site_config_dir, os.R_OK | os.W_OK)
        else pathlib.Path(DIRS.user_config_dir)
    )
    DATA = (
        pathlib.Path(DIRS.site_data_dir)
        if os.access(DIRS.site_data_dir, os.R_OK | os.W_OK)
        else pathlib.Path(DIRS.user_data_dir)
    )
    LOG = (
        DATA / 'log'
        if os.access(DIRS.site_data_dir, os.R_OK | os.W_OK)
        else pathlib.Path(DIRS.user_log_dir)
    )
    CACHE = (
        DATA / 'cache'
        if os.access(DIRS.site_data_dir, os.R_OK | os.W_OK)
        else pathlib.Path(DIRS.user_cache_dir)
    )
    CONFIG = pathlib.PurePath('config')
    DEFAULT = pathlib.PurePath('defaults')


class ConfigPathType(enum.Enum):
    DEFAULT: BasePath = BasePath.DEFAULT
    CONFIG: BasePath = BasePath.CONFIG


@enum.unique
class FileExt(enum.Enum):
    """Filename extensions used in gpm-playlist."""

    COMPRESSED: str = '.gz'
    YAML: str = '.yaml'
    COMPRESSED_YAML: str = ''.join((YAML, COMPRESSED))

    __slots__ = ()


@enum.unique
class LogLevel(enum.IntEnum):
    """Logging levels used in gpm-playlist."""

    CRITICAL: int = 50
    ERROR: int = 40
    WARNING: int = 30
    INFO: int = 20
    DEBUG: int = 10
    GENERATED: int = 5
    LOGGED_FUNC: int = 1

    __slots__ = ()

    @staticmethod
    def _log_this(self, level, message, *args, **kwargs):
        if self.isEnabledFor(level):
            self._log(level, message, args, **kwargs)

    @staticmethod
    def _adapter_log_this(self, level, message, *args, **kwargs):
        if self.isEnabledFor(level):
            self.log(level, message, args, **kwargs)

    def __init__(self, level: int) -> None:
        """Add level names to the Python logging system on creation."""
        if logging.getLevelName(level) != self.name:
            logging.addLevelName(level, self.name)
            setattr(
                logging.Logger,
                self.name.casefold(),  # type: ignore
                functools.partialmethod(  # type: ignore
                    self._log_this,
                    level
                )
            )
            setattr(
                logging.LoggerAdapter,
                self.name.casefold(),  # type: ignore
                functools.partialmethod(  # type: ignore
                    self._adapter_log_this,
                    level
                )
            )
