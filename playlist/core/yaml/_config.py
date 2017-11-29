"""
Module that encapsulates the implementation of :py:mod:`playlist.core.config`.

This provides a clean separation of implementation and interface. Generally
speaking, importing this module should not be necessary, but rather the
:py:mod:`playlist.core.config` module should be imported instead.

***************
Version History
***************


**********
Module API
**********

.. autosummary::
    :nosignatures:

    PathConfig
    RootConfig
    FileLoaded
    FileNotLoaded
"""
__all__ = (
    'PathConfig',
    'RootConfig',
    'FileLoaded',
    'FileNotLoaded'
)

import asyncio
import contextlib
import functools
import pathlib
import threading
import types
import typing
import weakref

import pkg_resources

from playlist.core import const, _config, lib
from playlist.core.yaml import async_yaml, sync_yaml


class FileLoadedType(metaclass=_config.SingletonMeta):
    """
    Value that a Config object's files are when loaded.

    This class doesn't really have any purpose besides being a placeholder
    when a Config's file is loaded. Once the element is not loaded, this
    placeholder changes to :py:class:`FileNotLoadedType`.
    """

    def __str__(self) -> str:
        """String version of the FileLoadedType object."""
        return 'File Loaded'

    def __repr__(self) -> str:
        """String representation of the FileLoadedType object."""
        return '<File Loaded>'

    def __bool__(self) -> bool:
        """Any instance of FileLoadedType is True."""
        return True

    def __hash__(self) -> int:
        """Hash value for the FileLoadedType object."""
        return hash(type(self).__name__)

    def __reduce__(self) -> tuple:
        """Used by pickling."""
        return (FileLoadedType, ())

    def __call__(self):
        """
        Any instance of FileLoadedType cannot be called.

        Raises:
            TypeError: Always, FileLoaded can't be called.
        """
        raise TypeError(
            "'{name}' object is not callable".format(
                name=type(self).__name__
            )
        )


FileLoaded = FileLoadedType()


class FileNotLoadedType(metaclass=_config.SingletonMeta):
    """
    Value that a Config object's files are when not loaded.

    This class doesn't really have any purpose besides being a placeholder
    when a Config's file isn't loaded yet. Once the element is loaded, this
    placeholder changes to :py:class:`FileLoadedType`.
    """

    def __str__(self) -> str:
        """String version of the FileNotLoadedType object."""
        return 'File Not Loaded'

    def __repr__(self) -> str:
        """String representation of the FileNotLoadedType object."""
        return '<File Not Loaded>'

    def __bool__(self) -> bool:
        """Any instance of FileNotLoadedType is False."""
        return False

    def __hash__(self) -> int:
        """Hash value for the FileNotLoadedType object."""
        return hash(type(self).__name__)

    def __reduce__(self) -> tuple:
        """Used by pickling."""
        return (FileNotLoadedType, ())

    def __call__(self):
        """
        Any instance of FileNotLoadedType cannot be called.

        Raises:
            TypeError: Always, FileNotLoaded can't be called.
        """
        raise TypeError(
            "'{name}' object is not callable".format(
                name=type(self).__name__
            )
        )


FileNotLoaded = FileNotLoadedType()


class YamlAsyncContextManager:
    def __init__(
        self,
        filepath: pathlib.PurePath,
        type_: const.ConfigPathType
    ) -> None:
        self._filepath = filepath
        self._type = type_
        self._count = 0
        self._lock = threading.Lock()

    @lib.inject_loop  # type: ignore
    async def __aenter__(
        self,
        *,
        loop: asyncio.AbstractEventLoop
    ) -> weakref.ProxyType:
        """Async context manager start."""
        await loop.run_in_executor(None, self._lock.acquire)
        try:
            self._count += 1
            try:
                return weakref.proxy(self._data)  # type: ignore

            except AttributeError:
                self._data = await async_yaml.yaml_read(
                    self._filepath,
                    self._type
                )
                return weakref.proxy(self._data)
        finally:
            await loop.run_in_executor(None, self._lock.release)

    @lib.inject_loop
    async def __aexit__(
        self,
        exc_type: type,
        exc_value: BaseException,
        tb: types.TracebackType,
        *,
        loop: asyncio.AbstractEventLoop
    ) -> None:
        """Async context manager end."""
        await loop.run_in_executor(None, self._lock.acquire)
        try:
            self._count -= 1

            if not self._count:
                del self._data
        finally:
            await loop.run_in_executor(None, self._lock.release)

    def __enter__(self) -> 'weakref.ProxyType':  # type: ignore
        with self._lock:
            self._count += 1
            try:
                return weakref.proxy(self._data)  # type: ignore

            except AttributeError:
                self._data = sync_yaml.yaml_read(self._filepath, self._type)
                return weakref.proxy(self._data)

    def __exit__(
        self,
        exc_type: type,
        exc_value: BaseException,
        tb: types.TracebackType
    ) -> None:
        with self._lock:
            self._count -= 1

            if not self._count:
                del self._data

    def _get_loaded(self) -> typing.Any:
        if hasattr(self, '_data'):
            return FileLoaded
        else:
            return FileNotLoaded

    def __repr__(self):
        """Return repr(self)."""
        return repr(self._get_loaded())

    def __str__(self):
        """Return str(self)."""
        return str(self._get_loaded())


class ConfigYamlAttr:
    def __init__(
        self,
        filepath: pathlib.PurePath,
        type_: const.ConfigPathType
    ) -> None:
        self._context_manager = YamlAsyncContextManager(filepath, type_)

    @property  # type: ignore
    def __doc__(self) -> str:  # type: ignore
        """Get attribute docstring."""
        return self._my_doc

    @__doc__.setter
    def __doc__(self, doc: str) -> None:
        self._my_doc = doc

    def __get__(self, inst: typing.Any, cls: type) -> YamlAsyncContextManager:
        """Get the value of this attribute."""
        return self._context_manager

    def __set__(
        self,
        inst: typing.Any,
        value: YamlAsyncContextManager
    ) -> None:
        """
        Unable to set a YAML attribute.

        Raises:
            AttributeError: Always, can't set a ConfigYamlAttr descriptor.
        """
        raise AttributeError("can't set attribute")

    def __delete__(self, inst: typing.Any) -> None:
        """
        Unable to delete a YAML attribute.

        Raises:
            AttributeError: Always, can't delete a ConfigYamlAttr descriptor.
        """
        raise AttributeError("can't delete attribute")

    def __repr__(self) -> str:
        """Return repr(self)."""
        return 'BLAH ' + repr(self._context_manager)

    def __str__(self) -> str:
        """Return str(self)."""
        return str(self._context_manager)


class PathConfig(
    _config.BaseConfig,
    bad_names={
        '_gen_resources',
        '_load_entries',
        '_set_path_attr',
        '__path',
        '__editable',
        '__extra_attrs',
    }
):
    """
    Class designed to translate a directory into a configuration entry.

    Sub-directories are also converted into being PathConfigs, so mapping a
    base path results in the entire hierarchy becoming available in the
    configuration object.

    Notes:
        * This is designed to work with the pkg_resources library. It expects
          that the path which is given exists under the :py:mod:`playlist.core`
          package.
        * With no parameters, this will construct a combined structure for
          both the ``playlist/core/config`` and ``playlist/core/defaults``
          paths.
        * YAML files are flagged to be loaded asynchronously.

    Warning:
        It is important that a path structure exists only in one of the
        two base paths (``playlist/core/config`` or
        ``playlist/core/defaults``). If a particular path exists in both, it
        will cause unexpected results as the path in the
        ``playlist/core/defaults`` tree will attempt to overwrite the entries
        in ``playlist/core/defaults``.
    """

    def __init__(
        self,
        path: pathlib.PurePath=pathlib.PurePath(''),
        type_: typing.Optional[const.ConfigPathType]=None,
        extra_attrs: typing.Optional[typing.List[dict]]=None
    ) -> None:
        """
        Initialize the PathConfig.

        Args:
            path (pathlib.PurePath): Specifies the path that will be checked
                for configuration files. If not specified, the
                :py:attr:`const.BasePath.CONFIG` will be used.
            editable (Optional[bool]): If set to True, it will load entries
                from the ``playlist/core/defaults`` path for the file, copy it
                to the user-editable location as a compressed YAML if it
                doesn't already exist there, so the user can edit the file.
                If set to False, it will load the path from
                ``playlist/core/config``. If not set at all, it loads from
                both paths.
            extra_attrs (Optional[List[dict]]): Additional attributes to add
                to the Config, following the format of the ``attrs``
                parameter for BaseConfig.
        """
        self.__path = pathlib.PurePath(path)
        self.__type = type_
        self.__extra_attrs = extra_attrs

        if type_ is None:
            tuple(
                self._load_entries(type_=path_type)  # type: ignore
                for path_type in const.ConfigPathType  # type: ignore
            )

        else:
            self._load_entries(type_=type_)

        super().__init__(attrs=extra_attrs)

    def _gen_resources(self, type_: const.ConfigPathType) -> typing.Generator[
        typing.Tuple[
            bool,
            str,
            pathlib.PurePath
        ],
        None,
        None
    ]:
        """
        Generate all of the resources for a path.

        It identifies files vs directories, and the complete filename,
        as well as the name that should be used for making entries in the
        :py:class:`PathConfig`.

        Args:
            editable (bool): True means start from ``playlist/core/default/``,
                False means start from ``playlist/core/config/``.

        Yields:
            Tuple[bool, str, pathlib.PurePath]: A three-element tuple that
            identifies if the item is a file or a directory, the name to use
            for further configuration, and the
            full path to the file or directory relative to the playlist
            package.
        """
        base = type_.value.value

        filepath = base / self.__path

        dirs = set()
        files = set()

        for entry in (
            pathlib.PurePath(item)
            for item in
            pkg_resources.resource_listdir(
                'playlist.core',
                filepath.as_posix()
            )
        ):
            full_entry = filepath / entry

            if pkg_resources.resource_isdir(
                'playlist.core',
                full_entry.as_posix()
            ):
                yield True, entry.name, full_entry
                dirs.add(entry.name)

            elif entry.suffix == const.FileExt.YAML.value:
                yield False, entry.stem, full_entry
                files.add(entry.name)

        if type_ == const.ConfigPathType.DEFAULT:
            default_path = filepath
            base = const.BasePath.SETTINGS.value
            filepath = base / self.__path
            with contextlib.suppress(FileNotFoundError):
                for editable_entry in filepath.iterdir():
                    directory_to_add = (
                        editable_entry.is_dir()
                        and editable_entry.name not in dirs
                    )
                    exists_in_defaults = (
                        pkg_resources.resource_isdir(
                            'playlist.core',
                            str(default_path / editable_entry.name)
                        )
                    )
                    file_to_add = (
                        not editable_entry.is_dir()
                        and editable_entry.stem not in files
                    )
                    is_compressed = (
                        editable_entry.suffix ==
                        const.FileExt.COMPRESSED.value
                    )
                    if directory_to_add and exists_in_defaults:
                        yield (
                            True,
                            editable_entry.name,
                            default_path / editable_entry.name
                        )

                    elif file_to_add and is_compressed:
                        yield (
                            False,
                            editable_entry.stem[
                                :-len(str(const.FileExt.YAML.value))
                            ],
                            default_path / editable_entry.name
                        )
                    else:
                        continue

    def _load_entries(self, type_: const.ConfigPathType) -> None:
        """
        Generate entries as attributes for the PathConfig object.

        This will recursively create new :py:class:`PathConfig` entries for
        each subfolder, or will set attributes to be loadable for any YAML
        files.

        Args:
            editable (bool): True means start from ``playlist/core/default/``,
                False means start from ``playlist/core/config/``.

        Yields:
            Optional[List[dict]]: Attributes defining YAML files and
            subfolders for the PathConfig, following the format of the
            ``attrs`` parameter for BaseConfig.
        """
        for is_dir, entry, filepath in self._gen_resources(type_):
            base = type_.value

            filepath = filepath.relative_to(base.value)

            if not is_dir:
                filepath = filepath.parent / entry

            self._set_path_attr(
                entry,
                is_dir,
                filepath,
                type_
            )

    def _set_path_attr(
        self,
        entry: str,
        is_dir: bool,
        filepath: pathlib.PurePath,
        type_: const.ConfigPathType
    ) -> None:
        if is_dir:
            super()._set_attr(
                name=entry,
                func=functools.partial(
                    PathConfig,
                    filepath,
                    type_
                ),
                doc='Config Sub-Path: {name}'.format(name=entry),
                preload=True
            )
        else:
            attr = ConfigYamlAttr(filepath, type_)
            self._funcs_ -= {entry}
            self._attrs_ |= {entry}
            self._setables_ -= {entry}
            setattr(type(self), entry, attr)

    def __reduce__(self) -> typing.Tuple[
            'PathConfig',
            typing.Tuple[typing.Any, ...],
            typing.Any
    ]:
        """Prepare the PathConfig for pickling."""
        return (  # type: ignore
            PathConfig,
            (str(self.__path), self.__editable, self.__extra_attrs),
            self.__getstate__()
        )


class RootConfig(PathConfig, _config.MainConfig):
    """
    Class used to define the ``playlist.core.config`` module.

    Contains the direct references to the various configuration files, which
    are lazily-loaded as necessary when accessed. They can be accessed as
    properties or as dictionary elements.
    """

    def __init__(self):
        """Initialize the MainConfig."""
        extra_attrs = (
            {
                'name': 'yaml_read_async',
                'func': lambda: async_yaml.yaml_read,
                'doc': async_yaml.yaml_read.__doc__,
                'preload': True,
            },

            {
                'name': 'yaml_write_async',
                'func': lambda: async_yaml.yaml_write,
                'doc': async_yaml.yaml_write.__doc__,
                'preload': True,
            },
            {
                'name': 'yaml_read_sync',
                'func': lambda: sync_yaml.yaml_read,
                'doc': sync_yaml.yaml_read.__doc__,
                'preload': True,
            },

            {
                'name': 'yaml_write_sync',
                'func': lambda: sync_yaml.yaml_write,
                'doc': sync_yaml.yaml_write.__doc__,
                'preload': True,
            },
        )
        super().__init__(extra_attrs=extra_attrs)

    def __reduce__(self):
        """Prepare the RootConfig for pickling."""
        return (RootConfig, (), self.__getstate__())
