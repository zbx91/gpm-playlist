"""Module containing the pandas code for gpm-playlist."""
__all__ = (
    'get_ins_upd_del',
)

import asyncio
import functools
import logging
import typing

import numpy
import pandas

from playlist.core import lib as corelib, logger


@logger.logged
def dict_to_df(
    data: typing.List[dict],
    index: typing.Union[str, typing.List[str]],
    type_: str,
    *,
    log: logging.Logger,
    log_opts: typing.Dict[str, str]
) -> typing.Tuple[
    str,
    typing.Dict[str, typing.Union[pandas.DataFrame, numpy.ndarray]]
]:
    """Convert intial list of dicts into a dataframe for current/previous."""
    try:
        df = pandas.DataFrame.from_records(data, index=index)
    except KeyError:
        if isinstance(index, str):
            index = pandas.Index(data=[], name=index)

        df = pandas.DataFrame(index=index)
    df = df.sort_index()
    log.debug(f'Converted {type_} to DataFrame of size {df.size}')
    return df


@logger.logged
def merge_entries(
    current: pandas.DataFrame,
    previous: pandas.DataFrame,
    *,
    log: logging.Logger,
    log_opts: typing.Dict[str, str]
) -> pandas.DataFrame:
    """Merge the current/previous dataframes by their index."""
    log.debug(
        f'Current entries: {current.size}; Previous entries: {previous.size}'
    )
    try:
        merged = current.merge(
            previous,
            how='outer',
            left_index=True,
            right_index=True
        )
        cols = current.columns
        ret_cols = set(cols.values)
    except ValueError:
        if current['data'].empty:
            cols = previous.columns
            ret_cols = set(cols.values)
            merged = previous.rename(columns=dict(zip(cols, cols + '_y')))
            merged = pandas.concat([
                merged,
                pandas.DataFrame(columns=(cols + '_x').values)
            ])
        else:
            cols = current.columns
            ret_cols = set(cols.values)
            merged = current.rename(columns=dict(zip(cols, cols + '_x')))
            merged = pandas.concat([
                merged,
                pandas.DataFrame(columns=(cols + '_y').values)
            ])
    log.debug(f'Merged entries: {merged.size}')
    return merged, ret_cols


def df_to_dict(data: pandas.DataFrame) -> typing.List[dict]:
    data = data.reset_index(level=data.index.names)
    ret_data = [
        {
            key: (
                value
                if not isinstance(value, str)
                else (
                    None
                    if value == 'None'
                    else int(value)
                    if corelib.is_int(value)
                    else float(value)
                    if corelib.is_number(value)
                    else bool(value)
                    if value in {'True', 'False'}
                    else value
                )
            )
            for key, value in row.items()
        }
        for row in data.to_dict('records')
    ]
    return ret_data


@logger.logged
def get_inserts(
    merged: pandas.DataFrame,
    curr_cols: numpy.ndarray,
    prev_cols: numpy.ndarray,
    *,
    log: logging.Logger,
    log_opts: typing.Dict[str, str]
) -> typing.Tuple[str, typing.List[dict]]:
    """Get the inserts (rows with current but no previous data)."""
    inserts = merged[~merged[prev_cols].notnull().T.any()]
    inserts = inserts[curr_cols]
    log.debug(f'Found {inserts.size} rows to insert.')
    if not inserts.empty:
        inserts = inserts.rename(
            columns=dict(zip(
                inserts.columns,
                inserts.columns.str.rstrip('x').str.rstrip('_').values
            ))
        )
        return 'inserts', df_to_dict(inserts)
    else:
        return 'inserts', []


@logger.logged
def get_deletes(
    merged: pandas.DataFrame,
    curr_cols: numpy.ndarray,
    prev_cols: numpy.ndarray,
    *,
    log: logging.Logger,
    log_opts: typing.Dict[str, str]
) -> typing.Tuple[str, typing.List[dict]]:
    """Get the deletes (rows with previous but no current data)."""
    deletes = merged[~merged[curr_cols].notnull().T.any()]
    deletes = deletes[prev_cols]
    log.debug(f'Found {deletes.size} rows to delete.')
    if not deletes.empty:
        deletes = deletes.rename(
            columns=dict(zip(
                deletes.columns,
                deletes.columns.str.rstrip('x').str.rstrip('_').values
            ))
        )
        return 'deletes', df_to_dict(deletes)
    else:
        return 'deletes', []


@logger.logged
def get_checks(
    merged: pandas.DataFrame,
    curr_cols: numpy.ndarray,
    prev_cols: numpy.ndarray,
    *,
    log: logging.Logger,
    log_opts: typing.Dict[str, str]
) -> pandas.DataFrame:
    """Get the checks (rows with both current and previous data)."""
    checks = merged[
        (merged[curr_cols].notnull().T.any())
        & (merged[prev_cols].notnull().T.any())
    ]
    log.debug(f'Found {checks.size} rows to check for updates.')
    return checks


@logger.logged
def split_checks(
    checks: pandas.DataFrame,
    cols: numpy.ndarray,
    type_: str,
    *,
    log: logging.Logger,
    log_opts: typing.Dict[str, str]
) -> typing.Tuple[str, pandas.DataFrame]:
    """Split the columns for current/previous from the checks."""
    df = checks[cols]
    if not df.empty:
        df = df.rename(
            columns=dict(zip(
                df.columns,
                df.columns.str.rstrip(
                    'x' if type_ == 'current' else 'y'
                ).str.rstrip('_').values
            ))
        )
    log.debug(f'Split {df.size} {type_} rows to check for updates.')
    return type_, df


@logger.logged
def get_updates(
    splits: typing.Dict[str, pandas.DataFrame],
    ignored: typing.Optional[typing.List[str]]=None,
    *,
    log: logging.Logger,
    log_opts: typing.Dict[str, str]
) -> typing.Tuple[str, typing.List[dict]]:
    """Get the updates (rows where data changed between current/previous)."""
    if splits['current'].empty:
        return 'updates', []
    if ignored:
        cols = [
            col
            for col in splits['current'].columns
            if col not in ignored
        ]
        if not cols:
            return 'updates', []
        current_checks = splits['current'][cols]
        previous_checks = splits['previous'][cols]
    else:
        current_checks = splits['current']
        previous_checks = splits['previous']

    current_checks = current_checks.fillna('')
    previous_checks = previous_checks.fillna('')

    updates = current_checks != previous_checks
    updates = updates.T.any()

    if ignored:
        updates = current_checks[updates]
        updates = updates.merge(
            splits['previous'][ignored],
            how='inner',
            left_index=True,
            right_index=True
        )
    else:
        updates = splits['current'][updates]
    log.debug(f'Found {updates.size} rows to update.')
    return 'updates', df_to_dict(updates)


@logger.logged
def get_skips(
    splits: typing.Dict[str, pandas.DataFrame],
    ignored: typing.Optional[typing.List[str]]=None,
    *,
    log: logging.Logger,
    log_opts: typing.Dict[str, str]
) -> typing.Tuple[str, typing.List[dict]]:
    """Get the skips (rows where data did not change."""
    if splits['current'].empty:
        return 'skips', []
    if ignored:
        cols = [
            col
            for col in splits['current'].columns
            if col not in ignored
        ]
        if not cols:
            return 'skips', df_to_dict(splits['previous'])
        current_checks = splits['current'][cols]
        previous_checks = splits['previous'][cols]
    else:
        current_checks = splits['current']
        previous_checks = splits['previous']

    current_checks = current_checks.fillna('')
    previous_checks = previous_checks.fillna('')

    skips = current_checks == previous_checks
    skips = skips.T.all()
    skips = splits['previous'][skips]
    log.debug(f'Found {skips.size} rows to skip.')
    return 'skips', df_to_dict(skips)


@corelib.inject_loop
@logger.logged
async def get_update_skips(
    merged: pandas.DataFrame,
    curr_cols: numpy.ndarray,
    prev_cols: numpy.ndarray,
    ignored: typing.Optional[typing.List[str]]=None,
    *,
    loop: asyncio.AbstractEventLoop,
    log: logging.Logger,
    log_opts: typing.Dict[str, str]
) -> typing.Tuple[
    str,
    typing.AsyncIterator[typing.Tuple[str, typing.List[dict]]]
]:
    """Retrieve the updates & skips for shared rows."""
    checks = await loop.run_in_executor(  # type: ignore
        None,
        functools.partial(
            get_checks,
            merged,
            curr_cols,
            prev_cols,
            log_opts=log_opts
        )
    )
    iterable: typing.Tuple[asyncio.Future, ...] = (
        loop.run_in_executor(  # type: ignore
            None,
            functools.partial(
                split_checks,
                checks,
                curr_cols,
                'current',
                log_opts=log_opts
            )
        ),
        loop.run_in_executor(  # type: ignore
            None,
            functools.partial(
                split_checks,
                checks,
                prev_cols,
                'previous',
                log_opts=log_opts
            )
        )
    )
    splits = {}
    async for key, value in corelib.task_map(corelib.coro_wrapper, iterable):
        splits[key] = value

    iterable = (
        loop.run_in_executor(  # type: ignore
            None,
            functools.partial(
                get_updates,
                splits,
                ignored=ignored,
                log_opts=log_opts
            )
        ),
        loop.run_in_executor(  # type: ignore
            None,
            functools.partial(
                get_skips,
                splits,
                ignored=ignored,
                log_opts=log_opts
            )
        )
    )
    return 'checks', corelib.task_map(corelib.coro_wrapper, iterable)


@logger.logged
@corelib.inject_loop
async def get_coro_data(
    type_: str,
    data_coro: typing.Coroutine[None, None, typing.List[dict]],
    index: typing.Union[str, typing.List[str]],
    *,
    loop: asyncio.AbstractEventLoop,
    log: logging.Logger,
    log_opts: typing.Dict[str, str]
) -> typing.Tuple[str, pandas.DataFrame]:
    collected = await data_coro
    return type_, await loop.run_in_executor(  # type: ignore
        None,
        functools.partial(
            dict_to_df,
            collected,
            index=index,
            type_=type_,
            log_opts=log_opts
        )
    )


@corelib.inject_loop
@logger.logged
async def get_ins_upd_del(
    data_name: str,
    curr_coro: typing.Coroutine[typing.List[dict], None, None],
    prev_coro: typing.Coroutine[typing.List[dict], None, None],
    index: typing.Union[str, typing.List[str]],
    ignored: typing.Optional[typing.List[str]]=None,
    *,
    loop: asyncio.AbstractEventLoop,
    log: logging.Logger,
    log_opts: typing.Dict[str, str]
) -> typing.Dict[str, typing.Union[typing.List[dict], typing.List[str], str]]:
    """
    Universal tool for determining inserts/updates/deletes/skips.

    Results are determined from the current and previous inputs, which must
    be lists of dicts that have the same keys in all dict entries in both
    inputs. From those, it figures out what changes are necessary and returns
    a dict containing the separate inserts/updates/deletes/skips groups.

    * **inserts** are rows that exist in the *current* but not *previous* data.
    * **deletes** are rows that exist in the *previous* but not *current* data.
    * **updates** are rows that exist in both *current* and *previous* data,
        and have changed.
    * **skips** are rows that exist in both *current* and *previous* data, and
        have not changed.

    Args:
        current (List[dict]): The current data records to match against.
        previous (List[dict]): The previous data records to match against.
        index (str): The name of the field in the data to use as an index.

    Note:
        `current` and `previous` are both *lists of dicts*, where the dicts
        must contain exactly the same keys for this code to work correctly.
        This is because the columns are matched up against each other for
        comparison.

    Returns:
        Dict[str, Union[List[dict]], List[str], str]: A dictionary containing
        an entry for *`'inserts'`*, *`'updates'`*, *`'deletes'`*, *`'skips'`*,
        and *`'index'`*. Each entry contains lists of dictionary records that
        belong to that particular category of data.
    """
    iterable: typing.Tuple[asyncio.Future, ...] = (
        get_coro_data('current', curr_coro, index=index),
        get_coro_data('previous', prev_coro, index=index)
    )

    collected = {}
    async for key, value in corelib.task_map(corelib.coro_wrapper, iterable):
        collected[key] = value

    log.info(
        ' '.join((
            f'{data_name} Collected:',
            f'curr ({collected["current"].size});',
            f'prev ({collected["previous"].size})',
        ))
    )

    merged, cols = await loop.run_in_executor(  # type: ignore
        None,
        functools.partial(
            merge_entries,
            log_opts=log_opts,
            **collected
        )
    )
    current_cols = [col + '_x' for col in cols]
    previous_cols = [col + '_y' for col in cols]

    iterable = (
        loop.run_in_executor(  # type: ignore
            None,
            functools.partial(
                get_inserts,
                merged,
                current_cols,
                previous_cols,
                log_opts=log_opts
            )
        ),
        loop.run_in_executor(  # type: ignore
            None,
            functools.partial(
                get_deletes,
                merged,
                current_cols,
                previous_cols,
                log_opts=log_opts
            )
        ),
        get_update_skips(
            merged,
            current_cols,
            previous_cols,
            ignored=ignored,
            log_opts=log_opts
        )
    )

    results = {}

    async for key, value in corelib.task_map(corelib.coro_wrapper, iterable):
        if key == 'checks':
            async for inner_key, inner_value in value:
                results[inner_key] = inner_value
        else:
            results[key] = value

    log.info(
        ' '.join((
            f'{data_name} Processed:',
            f'ins ({results["inserts"].__len__()});',
            f'upd ({results["updates"].__len__()});',
            f'del ({results["deletes"].__len__()});',
            f'skp ({results["skips"].__len__()})',
        ))
    )

    return results
