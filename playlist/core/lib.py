"""
Module containing standard functions available to be used in the gpm-playlist.

**********
Module API
**********

.. autosummary::
    :nosignatures:

    update
    is_int
    is_number
    Timer
    get_version

    inject_loop
    get_var_from_stack
    task_map
"""
__all__ = (
    # Universal tools
    'update',
    'is_int',
    'is_number',
    'Timer',
    'get_version',

    # Asynchronous tools
    'inject_loop',
    'get_var_from_stack',
    'task_map',
)

import asyncio
import collections
import collections.abc
import contextlib
import functools
import inspect
import typing

import arrow
import pkg_resources


def get_var_from_stack(var_name: str) -> typing.Any:
    """
    Retrieve the named variable from the call stack.

    Gets the first occurence of the named variable from the call stack and
    returns it.

    Args:
        var_name (str): The name of the variable to look for.

    Returns:
        Any: The variable's value from the call stack.

    Raises:
        NameError: If the variable is not found in the call stack.

    """
    frame = inspect.currentframe()
    while frame:
        with contextlib.suppress(KeyError):
            try:
                ret = frame.f_locals[var_name]
                break
            except KeyError:
                ret = frame.f_globals[var_name]
                break
        frame = frame.f_back
    else:
        raise NameError(f'{var_name} not found in the stack.')

    return ret


def _get_loop(new_loop=False) -> asyncio.AbstractEventLoop:
    if new_loop:
        loop = asyncio.new_event_loop()
    else:
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()

    return loop


def get_version():
    """Get the gpm-playlist version."""
    return pkg_resources.get_distribution('gpm_playlist').version


def inject_loop(func: typing.Callable) -> typing.Callable:
    """
    Add the main event loop to the decorated function.

    Requires a parameter: ``loop`` to be existing in the function. Will ensure
    that this parameter has the asyncio event loop injected into it.

    Args:
        func (Callable): The callable being decorated. It must have a ``loop``
        argument to be decorated.

    Returns:
        Callable: The decorated callable.

    """
    sig = inspect.signature(func)
    sig = sig.replace(
        parameters=[
            value
            if key != 'loop'
            else value.replace(default=None)
            for key, value in sig.parameters.items()
        ]
    )
    func.__signature__ = sig  # type: ignore

    def add_loop(
        args: typing.Tuple[typing.Any, ...],
        kwargs: typing.Dict[str, typing.Any]
    ) -> collections.OrderedDict:
        bargs = sig.bind(*args, **kwargs)
        bargs.apply_defaults()
        if bargs.arguments['loop'] is None:
            bargs.arguments['loop'] = _get_loop()

        return bargs.arguments  # type: ignore

    if inspect.isasyncgenfunction(func):  # type: ignore
        async def async_gen_loop_wrapper(
            *args: typing.Tuple[typing.Any, ...],
            **kwargs: typing.Dict[str, typing.Any]
        ) -> typing.AsyncGenerator:
            async for elem in func(**add_loop(args, kwargs)):
                yield elem
        ret = async_gen_loop_wrapper

    elif inspect.iscoroutinefunction(func):
        async def async_loop_wrapper(
            *args: typing.Tuple[typing.Any, ...],
            **kwargs: typing.Dict[str, typing.Any]
        ) -> typing.Coroutine:
            return await func(**add_loop(args, kwargs))
        ret = async_loop_wrapper  # type: ignore

    elif inspect.isgeneratorfunction(func):
        def gen_loop_wrapper(
            *args: typing.Tuple[typing.Any, ...],
            **kwargs: typing.Dict[str, typing.Any]
        ) -> typing.Generator:
            yield from func(**add_loop(args, kwargs))
        ret = gen_loop_wrapper  # type: ignore

    else:
        def func_loop_wrapper(
            *args: typing.Tuple[typing.Any, ...],
            **kwargs: typing.Dict[str, typing.Any]
        ) -> typing.Any:
            return func(**add_loop(args, kwargs))
        ret = func_loop_wrapper

    ret.__signature__ = sig  # type: ignore

    return functools.wraps(func)(ret)


async def task_map(
    coro: typing.Callable[[typing.Any], typing.Any],
    iterable: typing.Union[typing.AsyncIterable, typing.Iterable]
):
    """Map a coroutine to an iterable as an async generator."""
    item: typing.Any
    try:
        tasks = tuple(  # type: ignore
            asyncio.ensure_future(coro(item))
            async for item in typing.cast(typing.AsyncIterable, iterable)
        )
    except TypeError:
        tasks = tuple(
            asyncio.ensure_future(coro(item))
            for item in typing.cast(typing.Iterable, iterable)
        )

    for task in asyncio.as_completed(tasks):
        yield await typing.cast(typing.Awaitable, task)


class Timer(contextlib.ContextDecorator):
    """Class that is designed to time the execution of code."""

    async def __aenter__(self) -> 'Timer':
        """Async context manager start."""
        self.start = arrow.utcnow()

        with contextlib.suppress(AttributeError):
            del self.end

        with contextlib.suppress(AttributeError):
            del self.interval

        return self

    async def __aexit__(self, exc_type, exc_value, tb) -> None:
        """Async context manager end."""
        self.end = arrow.utcnow()
        self.interval = self.end - self.start

    @inject_loop
    def __enter__(self, *, loop: 'asyncio.AbstractEventLoop') -> 'Timer':
        """Context manager start."""
        return loop.run_until_complete(self.__aenter__())

    @inject_loop
    def __exit__(
        self,
        exc_type,
        exc_value,
        tb,
        *,
        loop: 'asyncio.AbstractEventLoop'
    ) -> None:
        """Context manager end."""
        loop.run_until_complete(self.__aexit__(exc_type, exc_value, tb))

    def total_seconds(self) -> typing.Optional[float]:
        """Return None, or the total number of seconds timed."""
        try:
            return self.interval.total_seconds()
        except AttributeError:
            return None

    @property
    def days(self) -> typing.Optional[int]:
        """None, or between -999999999 and 999999999 inclusive."""
        try:
            return self.interval.days
        except AttributeError:
            return None

    @property
    def seconds(self) -> typing.Optional[int]:
        """None, or between 0 and 86399 inclusive."""
        try:
            return self.interval.seconds
        except AttributeError:
            return None

    @property
    def microseconds(self) -> typing.Optional[int]:
        """None, or between 0 and 999999 inclusive."""
        try:
            return self.interval.microseconds
        except AttributeError:
            return None


@functools.lru_cache(maxsize=128)
def is_int(value: typing.Any) -> bool:
    """
    Determine if the given value is an integer or not.

    Args:
        value (Any): The value to check

    Returns:
        bool: True if an integer, False if not.

    """
    try:
        if value[0] in {'+', '-'}:
            return value[1:].strip().isdecimal()

        else:
            return value.strip().isdecimal()

    except (TypeError, AttributeError, IndexError):
        try:
            return int(value) == value

        except (TypeError, ValueError):
            return False


@functools.lru_cache(maxsize=128)
def is_number(value: typing.Any) -> bool:
    """
    Check if the given value is a number.

    Args:
        value (Any): The value to check

    Returns:
        bool: True if a number, False if not.

    """
    try:
        float(value)
        return True
    except (TypeError, ValueError):
        return False


def update(dest: dict, src: typing.Mapping) -> typing.Mapping:
    """
    Perform deep updates for data collections.

    Works for dictionary, list, and set elements of the dict.

    Args:
        dest (dict): The dict to update.
        src (dict): The dict to update with.

    Returns:
        dict: The completely updated dict

    """
    dest.update({
        key: (
            update(dest.get(key, {}), value)
            if isinstance(value, collections.abc.Mapping)

            else set(dest.get(key, set())) | set(value)
            if isinstance(value, collections.abc.Set)

            else list(dest.get(key, [])) + list(value)

            if not isinstance(value, (str, bytes, bytearray)) and all(
                isinstance(value, type_)
                for type_ in {
                    collections.abc.Sized,
                    collections.abc.Iterable,
                    collections.abc.Container,
                    collections.abc.Sequence
                }
            )

            else value
        )

        for key, value in src.items()
    })

    return dest
