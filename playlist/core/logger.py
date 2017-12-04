"""
Module that handles the logging system for playlist.

This provides a queue logging implementation that takes over the standard
Python logging, with the ability to automatically log to separate files for
each check for each application Playlist is checking. It also rolls over and
backs up the log files, compressing and storing them in a filename format
that certain BMW tools are able to identify as backups.

**********
Module API
**********

.. autosummary::
    :nosignatures:

    logged
    LogListener
    setup_logging
"""
__all__ = (
    'logged',
    'LogListener',
    'setup_logging',
)

import asyncio
import contextlib
import functools
import gzip
import inspect
import logging
import logging.config
import logging.handlers
import multiprocessing
import pathlib
import queue
import re
import time
import typing

import arrow
import pkg_resources
import ruamel.yaml

from playlist.core import const, lib

LOG_QUEUE: multiprocessing.Queue = multiprocessing.Queue(-1)
SETTINGS = ruamel.yaml.load(
    pkg_resources.resource_string(
        'playlist.core',
        (
            const.BasePath.CONFIG.value / 'log_settings'
        ).with_suffix(
            const.FileExt.YAML.value
        ).as_posix()
    ),
    Loader=ruamel.yaml.CLoader
)
FORMATTER = logging.Formatter(
    SETTINGS['formatters']['playlist']['format'],
    style=SETTINGS['formatters']['playlist']['style']
)


def _log_opts():
    try:
        log_opts = lib.get_var_from_stack('log_opts')
    except NameError:
        try:
            try:
                request = lib.get_var_from_stack('request')
                log_opts = request['log_opts']
            except NameError:
                app = lib.get_var_from_stack('app')
                log_settings = app['log_settings']
                log_opts = {
                    'log_queue': None,
                    'playlist_level': log_settings['playlist_level'],
                    'playlist_verbose': log_settings['playlist_level'],
                    'sql_level': log_settings['sql_level'],
                    'sql_verbose': log_settings['sql_level'],
                    'ssh_level': log_settings['ssh_level'],
                    'ssh_verbose': log_settings['ssh_level'],
                    'web_level': log_settings['web_level'],
                    'web_verbose': log_settings['web_level'],
                }
        except (KeyError, NameError):
            log_opts = {
                'log_queue': None,
                'playlist_level': const.LogLevel.RESULT,
                'playlist_verbose': const.LogLevel.RESULT,
                'sql_level': const.LogLevel.RESULT,
                'sql_verbose': const.LogLevel.RESULT,
                'ssh_level': const.LogLevel.RESULT,
                'ssh_verbose': const.LogLevel.RESULT,
                'web_level': const.LogLevel.RESULT,
                'web_verbose': const.LogLevel.RESULT,
            }
    return log_opts


class PlaylistRotatingFileHandler(logging.handlers.TimedRotatingFileHandler):
    """Logging handler used for Playlist logging files."""

    def __init__(self, filepath: pathlib.Path) -> None:
        """
        Initialize the handler.

        Args:
            *args: Positional arguments to pass to the superclass.
            **kwargs: Keyword arguments to pass to the superclass.
        """
        super().__init__(
            str(filepath),
            when='W0',
            interval=1,
            backupCount=6,
            encoding='utf-8',
            delay=True,
            atTime=arrow.get()
        )
        self.suffix = '%Y%m%d'
        self.extMatch = re.compile("(?P<suffix>\.log\d{4}\d{2}\d{2}\.gz)$")

        # Attempt to make rollovers actually happen!
        filepath = pathlib.Path(self.baseFilename)
        if filepath.exists():
            try:
                with filepath.open() as f:
                    date_str, millis = f.readline()[:23].split(',')
                first_entry_time = arrow.get(
                    date_str,
                    '%Y-%m-%d %H:%M:%S'
                )
                first_entry_time = first_entry_time.replace(
                    microsecond=first_entry_time.microsecond + (
                        int(millis) * 1000
                    )
                )
                t = first_entry_time.timestamp()

            except (ValueError, arrow.parser.ParserError):
                s = filepath.stat()
                t = min(s.st_mtime, s.st_ctime, s.st_atime)

        else:
            t = int(time.time())
        self.rolloverAt = self.computeRollover(t)

    def getFilesToDelete(self) -> typing.Iterator[str]:
        """
        Used to get files deleted at the right time.

        Excludes putting a '.' between .log and the date.

        Returns:
            Iterator[str]: The names of the files to be deleted.
        """
        filepath = pathlib.Path(self.baseFilename)
        pattern = ''.join((filepath.name, '*'))

        match_gen = (
            self.extMatch.search(filename.name)
            for filename in filepath.parent.glob(pattern)
        )

        result = sorted(
            (
                filepath.with_suffix(match.group('suffix'))
                for match in match_gen
                if match
            ),
            reverse=True
        )[self.backupCount:]

        return map(str, result)

    def rotation_filename(self, default_name: str) -> str:
        """
        Get the filename to use for logfile rotation.

        Args:
            default_name (str): The default filename to use.

        Returns:
            str: The name to use based on the default.
        """
        filepath = pathlib.Path(default_name)
        filename = pathlib.PurePath(filepath.stem).stem
        suffix = ''.join((
            '.',
            'log',
            filepath.suffix.lstrip('.'),
            const.FileExt.COMPRESSED.value
        ))
        filepath = filepath.with_name(filename)
        filepath = filepath.with_suffix(suffix)

        return str(filepath)

    def rotate(self, source: str, dest: str) -> None:
        """
        Rotate the log files.

        This will compress the files as gzipped versions of them on rotation,
        as well as rename the files.

        Args:
            source (str): The source filename to use.
            dest (str): The destination filename to use.
        """
        source_path = pathlib.Path(source)
        dest_path = pathlib.Path(dest)
        with source_path.open('rb') as sf,\
                gzip.open(str(dest_path), 'wb') as df:
            df.write(sf.read())

        source_path.unlink()


class PlaylistQueueHandler(logging.handlers.QueueHandler):
    def emit(self, record: logging.LogRecord) -> None:
        try:
            log_opts = _log_opts()
            record = self.prepare(record)
            if record.name.startswith('asyncssh'):
                lvl_type = 'ssh'
            elif record.name.startswith('aiohttp'):
                lvl_type = 'web'
            elif record.name.startswith('sqlalchemy.engine'):
                lvl_type = 'sql'
            else:
                lvl_type = 'playlist'
            log_level = log_opts[f'{lvl_type}_level']
            verbose = log_opts[f'{lvl_type}_verbose']
            rec_level = const.LogLevel[record.levelname]
            if rec_level >= log_level:
                self.enqueue(record)
            if rec_level >= verbose:
                if (
                    record.name.startswith('sqlalchemy.engine')
                    and verbose < const.LogLevel.DEBUG
                ):
                    record.msg = '\n'.join((
                        f'-- SQLALCHEMY [{record.levelname}] --',
                        record.msg,
                        '--'
                    ))
                log_queue = log_opts.get('log_queue', None)
                with contextlib.suppress(AttributeError):
                    log_queue.put_nowait(record)

        except Exception:
            self.handleError(record)


class LogListener:
    """
    Modification of :py:class:`logging.handlers.QueueListener`.

    This class is a modification of the logging.handlers.QueueListener that
    accomplishes two different things. First, it uses a multiprocessing.Process
    rather than a threading.Thread, and is used with a multiprocessing.Queue
    instead of a queue.Queue. Second, it relies on special logging filters
    to tag the log records to properly separate out and distinguish the correct
    handlers to use for
    This class implements an internal threaded listener which watches for
    LogRecords being added to a queue, removes them and passes them to a
    list of handlers for processing.
    """

    def __init__(self) -> None:
        """Initialise an instance with the specified queue and handlers."""
        self._process: typing.Optional[multiprocessing.Process] = None
        self._lock = asyncio.Lock()
        self._count = 0
        self._handlers: typing.Dict[
            typing.Tuple[typing.Optional[str], typing.Optional[str]],
            PlaylistRotatingFileHandler
        ] = {}

    def dequeue(self, block: bool) -> logging.LogRecord:
        """
        Dequeue a record and return it, optionally blocking.

        The base implementation uses get. You may want to override this method
        if you want to use timeouts or work with custom queue implementations.
        """
        return LOG_QUEUE.get(block)

    @lib.inject_loop
    async def start(self, *, loop: asyncio.AbstractEventLoop) -> None:
        """
        Start the listener.

        This starts up a background process to monitor the queue for
        LogRecords to process.
        """
        self._process = p = await loop.run_in_executor(
            None,
            functools.partial(
                multiprocessing.Process,
                target=self._monitor
            )
        )
        p.daemon = True
        p.start()

    async def __aenter__(self) -> 'LogListener':
        """Async context manager enter."""
        async with self._lock:
            if not self._count:
                await self.start()
            self._count += 1
        return self

    def prepare(self, record: logging.LogRecord) -> logging.LogRecord:
        """Prepare a record for handling."""
        return record

    def _get_handler(self) -> PlaylistRotatingFileHandler:
        try:
            return self.__handler
        except AttributeError:
            path = const.BasePath.LOG.value
            path.mkdir(parents=True, exist_ok=True)

            filepath = (path / 'main').with_suffix('.log')
            handler = PlaylistRotatingFileHandler(filepath)
            handler.setLevel(const.LogLevel.LOGGED_FUNC.value)
            handler.setFormatter(FORMATTER)
            self.__handler = handler
            return self.__handler

    def handle(self, record: logging.LogRecord) -> None:
        """
        Handle a record.

        This just loops through the handlers offering them the record
        to handle.
        """
        record = self.prepare(record)

        handler = self._get_handler()

        handler.handle(record)

    def _monitor(self) -> None:
        """
        Monitor the queue for records, and ask the handler to deal with them.

        This method runs on a separate, internal process.
        The process will terminate if it sees a sentinel object in the queue.
        """
        while True:
            try:
                record = self.dequeue(True)
                if record is None:
                    break
                self.handle(record)
            except queue.Empty:
                break
        for handler in self._handlers.values():
            handler.flush()
            handler.close()

    @lib.inject_loop
    async def enqueue_sentinel(
        self,
        *,
        loop: asyncio.AbstractEventLoop
    ) -> None:
        """
        Enqueue the sentinel record.

        The base implementation uses put_nowait. You may want to override this
        method if you want to use timeouts or work with custom queue
        implementations.
        """
        await loop.run_in_executor(None, LOG_QUEUE.put_nowait, None)

    async def stop(self) -> None:
        """
        Stop the listener.

        This asks the process to terminate, and then waits for it to do so.
        Note that if you don't call this before your application exits, there
        may be some records still left on the queue, which won't be processed.
        """
        await self.enqueue_sentinel()
        self._process.join()
        self._process = None

    async def __aexit__(
        self,
        *args: typing.Tuple[typing.Any, ...],
        **kwargs: typing.Dict[str, typing.Any]
    ) -> None:
        """Async context manager exit."""
        async with self._lock:
            self._count -= 1
            if not self._count:
                await self.stop()


@contextlib.contextmanager  # type: ignore
def _log_wrapper(
    func: typing.Callable,
    type_: str,
    sig: inspect.Signature,
    args: typing.Tuple[typing.Any, ...],
    kwargs: typing.Dict[str, typing.Any],
    list_: bool
) -> typing.ContextManager[typing.List[str]]:
    log = logging.getLogger(func.__module__)

    if 'log_opts' in sig.parameters and not kwargs.get('log_opts', None):
        kwargs['log_opts'] = _log_opts()

    if 'log' in sig.parameters and not kwargs.get('log', None):
        kwargs['log'] = log

    bargs = sig.bind(*args, **kwargs)

    logged_func_enabled = log.isEnabledFor(const.LogLevel.LOGGED_FUNC)

    results = []
    if logged_func_enabled:
        log.logged_func(f'{type_} {func.__name__} [BEGIN]: {bargs!r}')
        start = arrow.get()

    try:
        yield results, bargs.arguments
    except Exception as e:
        if logged_func_enabled:
            log.logged_func(
                f'{type_} {func.__name__} [{e.__class__.__name__}]: {e!s}'
            )
        raise

    else:
        if logged_func_enabled:
            if len(results) == 1:
                results = results[0]
            else:
                results = tuple(results)
            end_msg = f'returns: {results!r}'
            interval = arrow.get() - start
            log.logged_func(
                f'{type_} {func.__name__} [END] ({interval}): {end_msg}'
            )


def logged(func: typing.Callable) -> typing.Callable:
    """
    Wrap callable with logging entries.

    There will be two logging entries:
        * the first will mark when the callable started, along with all
          parameters.
        * the second will mark when the callable ended, along with the return
          value and the time it took to execute the function.

    It will identify the callable as a FUNCTION, GENERATOR, or COROUTINE.

    Warning:
        Use this decorator sparingly, as it can make VERY VERBOSE
        LogLevel.GENERATED entries in the log. and makes it somewhat
        difficult to dig through logs at that level.

    Args:
        func (Callable): The callable to log.

    Returns:
        Callable: The decorated callable.
    """
    sig = inspect.signature(func)
    if 'log' in sig.parameters:
        sig = sig.replace(
            parameters=[
                value
                if key != 'log'
                else value.replace(default=None)
                for key, value in sig.parameters.items()
            ]
        )
        func.__signature__ = sig

    if inspect.isasyncgenfunction(func):
        async def logged_async_gen(*args, **kwargs):
            with _log_wrapper(
                func,
                '---- ASYNC GENERATOR ----',
                sig,
                args,
                kwargs,
                list_=True
            ) as (results, fargs):
                async for entry in func(**fargs):
                    yield entry
                    results.append(entry)

        ret = logged_async_gen

    elif inspect.iscoroutinefunction(func):
        async def logged_coro(*args, **kwargs):
            with _log_wrapper(
                func,
                '<<<< COROUTINE >>>>',
                sig,
                args,
                kwargs,
                list_=False
            ) as (results, fargs):
                results.append(await func(**fargs))
                return results[-1]

        ret = logged_coro

    elif inspect.isgeneratorfunction(func):
        def logged_gen(*args, **kwargs):
            with _log_wrapper(
                func,
                '|||| GENERATOR ||||',
                sig,
                args,
                kwargs,
                list_=True
            ) as (results, fargs):
                for entry in func(**fargs):
                    yield entry
                    results.append(entry)

        ret = logged_gen

    else:
        def logged_func(*args, **kwargs):
            with _log_wrapper(
                func,
                ':::: FUNCTION ::::',
                sig,
                args,
                kwargs,
                list_=False
            ) as (results, fargs):
                results.append(func(**fargs))
                return results[-1]

        ret = logged_func

    ret.__signature__ = sig

    return functools.wraps(func)(ret)


def setup_logging() -> None:
    """Configure the logging system."""
    logging.config.dictConfig(SETTINGS)
