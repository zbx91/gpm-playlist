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
"""
import asyncio  # NOQA
import functools
import gzip
import pathlib
import pprint
import sys
import typing

import aiofiles
import pkg_resources
import ruamel.yaml

from playlist.core import const, _config, logger, lib


__all__ = (
    'yaml_read',
    'yaml_write'
)


@lib.inject_loop
async def _read_gzip(
    filepath: 'pathlib.Path',
    *,
    loop: 'asyncio.AbstractEventLoop'
) -> str:
    async with aiofiles.open(str(filepath), mode='rb') as inp:
        compressed_bytes = await inp.read()
    byte_data = await loop.run_in_executor(
        None,
        gzip.decompress,
        compressed_bytes
    )
    return await loop.run_in_executor(
        None,
        byte_data.decode,
        'utf8'
    )


@lib.inject_loop
async def _write_gzip(
    filepath: 'pathlib.Path',
    data: str,
    *,
    loop: 'asyncio.AbstractEventLoop'
) -> None:
    byte_data = await loop.run_in_executor(None, data.encode, 'utf8')
    compressed_bytes = await loop.run_in_executor(
        None,
        gzip.compress,
        byte_data
    )
    async with aiofiles.open(str(filepath), mode='wb') as out:
        await out.write(compressed_bytes)


@logger.logged
@lib.inject_loop
async def _yaml_load_default(
    type_: 'const.ConfigPathType',
    data_filepath: 'pathlib.Path',
    subpath: 'typing.Union[str, pathlib.PurePath]',
    filename: str,
    *,
    loop: 'asyncio.AbstractEventLoop',
    log: 'logger.PlaylistLogger'
) -> None:
    try:
        if subpath.is_absolute():  # type: ignore
            resource_subpath = subpath.relative_to(  # type: ignore
                const.BasePath.SETTINGS.value
            )
        else:
            resource_subpath = subpath
    except AttributeError:
        resource_subpath = subpath
    default_filepath = type_.value.value / resource_subpath / filename

    yaml_bytes = await loop.run_in_executor(
        None,
        pkg_resources.resource_string,
        'playlist.core',
        default_filepath.as_posix()
    )

    yaml_str = await loop.run_in_executor(None, yaml_bytes.decode, 'utf8')
    log_msg = ' '.join((
        'Compressing {path!s} from resource {resource!r}',
        'to {gzip_path!s}'
    )).format(
        path=default_filepath.as_posix(),
        resource='playlist.core',
        gzip_path=data_filepath
    )

    log.debug(log_msg)

    await _write_gzip(data_filepath, yaml_str)


@logger.logged
@lib.inject_loop
async def _yaml_read_editable(
    type_: 'const.ConfigPathType',
    subpath: 'pathlib.Path',
    filename: str,
    *,
    loop: 'asyncio.AbstractEventLoop',
    log: 'logger.PlaylistLogger',
) -> 'typing.Any':
    if type_ == const.ConfigPathType.DEFAULT:
        data_filepath = const.BasePath.SETTINGS.value / subpath
        await loop.run_in_executor(
            None,
            functools.partial(data_filepath.mkdir, parents=True, exist_ok=True)
        )

    else:
        raise ValueError(f'Incorrect Config Path Type: {type_}')

    data_filepath /= filename

    data_filepath = data_filepath.with_suffix(
        const.FileExt.COMPRESSED_YAML.value
    )

    try:
        yaml_str = await _read_gzip(data_filepath)
    except FileNotFoundError:
        await _yaml_load_default(
            type_,
            data_filepath,
            subpath,
            filename
        )
        yaml_str = await _read_gzip(data_filepath)

    data = await loop.run_in_executor(  # type: ignore
        None,
        functools.partial(
            ruamel.yaml.load,
            yaml_str,
            Loader=ruamel.yaml.CLoader
        )
    )

    logging_lines = (
        '/---------- YAML Read ----------\\',
        str(data_filepath),
        '|------------ FROM -------------|',
        yaml_str,
        '|------------- TO --------------|',
        pprint.pformat(data),
        '\\-------------------------------/'
    )
    log_msg = '\n'.join(logging_lines)

    log.generated(log_msg)

    return data


@logger.logged
@lib.inject_loop
async def _yaml_read_config(
    subpath: 'pathlib.PurePath',
    filename: str,
    *,
    loop: 'asyncio.AbstractEventLoop',
    log: 'logger.PlaylistLogger'
) -> 'typing.Any':
    config_filepath = const.BasePath.CONFIG.value / subpath / filename
    yaml_str = await loop.run_in_executor(
        None,
        pkg_resources.resource_string,
        'playlist.core',
        config_filepath.as_posix()
    )
    data = await loop.run_in_executor(  # type: ignore
        None,
        functools.partial(
            ruamel.yaml.load,
            yaml_str,
            Loader=ruamel.yaml.CLoader
        )
    )
    logging_lines = (
        '/---------- YAML Read ----------\\',
        '{filepath!s} (resource={resource!r})'.format(
            filepath=config_filepath.as_posix(),
            resource='playlist.core'
        ),
        '|------------ FROM -------------|',
        str(yaml_str, encoding='utf-8'),
        '|------------- TO --------------|',
        pprint.pformat(data),
        '\\-------------------------------/'
    )
    log_msg = '\n'.join(logging_lines)
    log.generated(log_msg)

    return data


@logger.logged
async def yaml_read(
    filepath: pathlib.PurePath,
    type_: const.ConfigPathType=const.ConfigPathType.CONFIG
) -> typing.Any:
    """
    Read a YAML file and convert it into a Config object.

    Args:
        filepath (pathlib.PurePath): The relative path to the YAML file being
            read. Do not add the ``.yaml`` or ``.yaml.gz`` to the end of the
            filename, this will be added automatically.
        editable (bool): If set to True, the original file must be in the
            playlist/core/defaults directory, and will be copied as a
            compressed file into the correct user-accessible location to
            permit user editing. This is used for
            :py:attr:`playlist.core.config.settings`.  Defaults to False.

    Returns:
        Any: The Config object compatable form of the data from the YAML
        file. Typically, this will be a :py:class:`DictConfig`,
        :py:class:`tuple`, or :py:class:`frozenset`.

    Note:
        Why is gzip used? Because it is much faster compression/decompression
        than bzip2, xz, or even zip. Further, it actually compresses small
        datafiles (like what playlist has) better than the alternatives.

        Gzip is so firmly embraced in Linux that most standard tools either
        natively read/write gzip-compressed files (like vi), or have an
        alternative gzip-handling equivalent (like zcat for cat).

        Smaller files results in less File I/O, which improves the overall
        performance of checks, as filesystems are substantially slower than
        RAM -- it takes less time and resources to simply read a small
        compressed file and decompress it into memory than the leave the
        files uncompressed and read them straight from the filesystem.

    References:
        :py:func:`playlist.core.config.yaml_read`,
        :py:func:`parse_element`,
        :py:class:`DictConfig`,
        :py:class:`tuple`,
        :py:class:`frozenset`

    """
    filepath = filepath.with_suffix(const.FileExt.YAML.value)
    subpath = filepath.parent
    filename = filepath.name

    if type_ == const.ConfigPathType.CONFIG:
        data = await _yaml_read_config(subpath, filename)

    else:
        data = await _yaml_read_editable(type_, subpath, filename)

    return _config.parse_element(data)


@logger.logged
@lib.inject_loop
async def yaml_write(
    filepath: 'pathlib.PurePath',
    data: 'typing.Any',
    *,
    loop: 'asyncio.AbstractEventLoop',
    log: 'logger.PlaylistLogger'
) -> None:
    """
    Convert the data into YAML, writing it to the file system.

    Args:
        filepath (pathlib.PurePath): The relative path to the YAML file being
            written to.  Do not add the .yaml.gz to the end of the filename,
            this will be added automatically.
        data: The data structure that will be converted to YAML.

    References:
        :py:func:`playlist.core.config.yaml_write`

    """
    if not data:
        raise RuntimeError('Data is empty, cannot write file.')

    filepath = filepath.with_suffix(const.FileExt.COMPRESSED_YAML.value)

    subpath = filepath.parent
    filename = filepath.name

    data_filepath = const.BasePath.SETTINGS.value / subpath
    await loop.run_in_executor(
        None,
        functools.partial(data_filepath.mkdir, parents=True, exist_ok=True)
    )
    data_filepath /= filename

    yaml_dump_params = {
        'default_flow_style': False,
        'indent': 4,
        'width': sys.maxsize,
    }

    yaml_data = await loop.run_in_executor(  # type: ignore
        None,
        functools.partial(
            ruamel.yaml.safe_dump,
            **yaml_dump_params
        ),
        data,
    )

    logging_lines = (
        '/:::::::::: YAML Write ::::::::::\\',
        str(data_filepath),
        '|::::::::::::: FROM :::::::::::::|',
        pprint.pformat(data),
        '|:::::::::::::: TO ::::::::::::::|',
        yaml_data,
        '\\::::::::::::::::::::::::::::::::/'
    )
    log_msg = '\n'.join(logging_lines)
    log.generated(log_msg)

    await _write_gzip(data_filepath, yaml_data)
