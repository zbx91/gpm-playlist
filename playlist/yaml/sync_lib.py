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

import gzip
import pathlib
import pprint
import sys
import typing

import pkg_resources
import ruamel.yaml

from playlist.core import const, _config, logger


__all__ = (
    'yaml_read',
    'yaml_write'
)


def _read_gzip(
    filepath: 'pathlib.Path',
) -> str:
    with gzip.open(str(filepath), mode='rb') as inp:
        return str(inp.read(), 'utf8')


def _write_gzip(
    filepath: 'pathlib.Path',
    data: str,
) -> None:
    with gzip.open(str(filepath), mode='wb') as out:
        out.write(bytes(data, 'utf8'))


@logger.logged
def _yaml_load_default(
    type_: 'const.ConfigPathType',
    data_filepath: 'pathlib.Path',
    subpath: 'typing.Union[str, pathlib.PurePath]',
    filename: str,
    *,
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

    yaml_bytes = pkg_resources.resource_string(
        'playlist.core',
        default_filepath.as_posix()
    )

    yaml_str = yaml_bytes.decode('utf8')
    log_msg = ' '.join((
        'Compressing {path!s} from resource {resource!r}',
        'to {gzip_path!s}'
    )).format(
        path=default_filepath.as_posix(),
        resource='playlist.core',
        gzip_path=data_filepath
    )

    log.debug(log_msg)

    return _write_gzip(data_filepath, yaml_str)


# class _EType(enum.Enum):
#     Mapping: int = 1
#     Sequence: int = 2
#     Set: int = 3
#     Other: int = 4
#
#     @classmethod
#     def get(cls, elem: typing.Any) -> '_EType':
#         if isinstance(elem, collections.abc.Mapping):
#             return cls.Mapping
#
#         elif isinstance(elem, collections.abc.Set):
#             return cls.Set
#
#         elif isinstance(elem, (str, bytes, bytearray)):
#             return cls.Other
#
#         elif isinstance(elem, collections.Sequence):
#             return cls.Sequence
#
#         else:
#            return cls.Other


# async def _yaml_merge(src, dest):
#     src_type = _EType.get(src)
#     dest_type = _EType.get(dest)
#
#     if dest_type != src_type:
#         raise ValueError('\n'.join((
#             'Source and Destination must be the same type of data to merge.',
#             '>> Source: {src_type.name}',
#             '{src}',
#             '<< Destination: {dest_type.name}',
#             '{dest}'
#         )).format(
#             src_type=src_type,
#             dest_type=dest_type,
#             src=pprint.pformat(src),
#             dest=pprint.pformat(dest)
#         ))
#
#     elif dest_type == _EType.Mapping:
#         ret = await loop.run_in_executor(
#             None,
#             ruamel.yaml.comments.CommentedMap
#         )
#
#         for key, value in dest.items():
#             if key not in src:
#                 ret[key] = value
#             else:
#                 ret[key] = await _yaml_merge(src[key], value)
#
#         for key, value in src.items():
#             if key not in dest:
#                 ret[key] = value
#
#     elif dest_type == _EType.Sequence:
#         ret = await loop.run_in_executor(
#             None,
#             ruamel.yaml.comments.CommentedSeq
#         )
#         for elem in dest:
#             if elem in src:
#                 ret.append(await _yaml_merge(src[src.index(elem)], elem))
#             else:
#                 ret.append(elem)
#
#         for elem in src:
#             if elem not in dest:
#                 ret.append(elem)
#
#     elif dest_type == _EType.Set:
#         ret = await loop.run_in_executor(
#             None,
#             ruamel.yaml.comments.CommentedSet
#         )
#         ret |= dest
#         ret ^= src
#
#         src_seq = await loop.run_in_executor(
#             None,
#             ruamel.yaml.comments.CommentedSeq
#         )
#         for elem in src - ret:
#             src_seq.append(elem)
#         src_seq.sort()
#
#         dest_seq = await loop.run_in_executor(
#             None,
#             ruamel.yaml.comments.CommentedSeq
#         )
#         for elem in dest - ret:
#             dest_seq.append(elem)
#         dest_seq.sort()
#
#         for ndx, src_elem in src_seq:
#             ret.add(await _yaml_merge(src_elem, dest_seq[ndx]))
#
#     else:
#         ret = src
#
#     if dest_type in {_EType.Mapping, _EType.Sequence, _EType.Set}:
#         try:
#             ret_comments = ret.ca
#         except AttributeError:
#             return ret
#
#         try:
#             dest_comments = dest.ca
#         except AttributeError:
#             dest_comments = None
#
#         try:
#             src_comments = src.ca
#         except AttributeError:
#             src_comments = None
#
#         if dest_comments is None and src_comments is None:
#             return ret
#
#         elif src_comments is None:
#             ret_comments.start = dest_comments.start
#             ret_comments.end = dest_comments.end
#             await loop.run_in_executor(
#                 None,
#                 ret_comments.items.update,
#                 dest_comments.items
#             )
#
#         elif dest_comments is None:
#             ret_comments.start = src_comments.start
#             ret_comments.end = src_comments.end
#             await loop.run_in_executor(
#                 None,
#                 ret_comments.items.update,
#                 src_comments.items
#             )
#
#         else:
#             try:
#                 ret_comments.start = src_comments.start or\
#                     dest_comments.start
#             except AttributeError:
#                 with contextlib.suppress(AttributeError):
#                     ret_comments.start = dest_comments.start
#
#             try:
#                 ret_comments.end = src_comments.end or dest_comments.end
#             except AttributeError:
#                 with contextlib.suppress(AttributeError):
#                     ret_comments.end = dest_comments.end
#
#             try:
#                 merged_items = dest_comments.items
#             except AttributeError:
#                 merged_items = {}
#             with contextlib.suppress(AttributeError):
#                 await loop.run_in_executor(
#                     None,
#                     merged_items.update,
#                     src_comments.items
#                 )
#
#             await loop.run_in_executor(
#                 None,
#                 ret_comments.items.update,
#                 merged_items
#             )
#
#     return ret


@logger.logged
def _yaml_read_editable(
    type_: 'const.ConfigPathType',
    subpath: 'pathlib.Path',
    filename: str,
    *,
    log: 'logger.PlaylistLogger',
) -> 'typing.Any':
    if type_ == const.ConfigPathType.DEFAULT:
        data_filepath = const.BasePath.SETTINGS.value / subpath
    else:
        raise ValueError(f'Incorrect Config Path Type: {type_}')

    data_filepath.mkdir(parents=True, exist_ok=True)
    data_filepath /= filename
    data_filepath = data_filepath.with_suffix(
        const.FileExt.COMPRESSED_YAML.value
    )

    try:
        yaml_str = _read_gzip(data_filepath)
    except FileNotFoundError:
        _yaml_load_default(
            type_,
            data_filepath,
            subpath,
            filename
        )
        yaml_str = _read_gzip(data_filepath)

    data = ruamel.yaml.load(yaml_str, Loader=ruamel.yaml.CLoader)

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
def _yaml_read_config(
    subpath: 'pathlib.PurePath',
    filename: str,
    *,
    log: 'logger.PlaylistLogger'
) -> 'typing.Any':
    config_filepath = const.BasePath.CONFIG.value / subpath / filename
    yaml_str = pkg_resources.resource_string(
        'playlist.core',
        config_filepath.as_posix()
    )
    data = ruamel.yaml.load(
        yaml_str,
        Loader=ruamel.yaml.CLoader
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
def yaml_read(
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
        data = _yaml_read_config(subpath, filename)

    else:
        data = _yaml_read_editable(type_, subpath, filename)

    return _config.parse_element(data)


@logger.logged
def yaml_write(
    filepath: 'pathlib.PurePath',
    data: 'typing.Any',
    *,
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
    data_filepath.mkdir(parents=True, exist_ok=True)
    data_filepath /= filename

    yaml_dump_params = {
        'default_flow_style': False,
        'indent': 4,
        'width': sys.maxsize,
    }

    yaml_data = ruamel.yaml.safe_dump(
        data,
        **yaml_dump_params
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

    return _write_gzip(data_filepath, yaml_data)
