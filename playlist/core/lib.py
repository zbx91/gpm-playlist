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
    strip_tags
    Timer

    parse_email_addrs
    validate_email

    make_coro
    async_open_file
    change_default_executor
    AsyncContextManager
    AsyncIterator

    EnvironConfig
"""

import asyncio
import base64
import collections
import collections.abc
import contextlib
import functools
import inspect
import os
import struct
import typing
import zlib

import arrow
import cryptography
import cryptography.fernet
import cryptography.hazmat.primitives
import cryptography.hazmat.primitives.kdf.pbkdf2
import pkg_resources

from playlist.core import const


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


@inject_loop
async def _get_key_async(
    salt: bytes,
    *,
    loop: 'asyncio.AbstractEventLoop'
) -> bytes:
    """Generate a 32-byte key to use in encryption/decryption."""
    password = await loop.run_in_executor(
        None,
        bytes,
        __name__,
        const.ENCODING
    )
    kdf = await loop.run_in_executor(
        None,
        functools.partial(
            cryptography.hazmat.primitives.kdf.pbkdf2.PBKDF2HMAC,
            algorithm=cryptography.hazmat.primitives.hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
            backend=cryptography.hazmat.backends.default_backend()
        )
    )
    derived = await loop.run_in_executor(
        None,
        kdf.derive,
        password
    )
    return await loop.run_in_executor(None, base64.urlsafe_b64encode, derived)


def _get_key_sync(salt: bytes) -> bytes:
    """Generate a 32-byte key to use in encryption/decryption."""
    password = bytes(__name__, const.ENCODING)
    kdf = cryptography.hazmat.primitives.kdf.pbkdf2.PBKDF2HMAC(
        algorithm=cryptography.hazmat.primitives.hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100000,
        backend=cryptography.hazmat.backends.default_backend()
    )
    derived = kdf.derive(password)
    return base64.urlsafe_b64encode(derived)


@inject_loop
async def encrypt_async(
    data: str,
    *,
    loop: 'asyncio.AbstractEventLoop'
) -> str:
    """Encrypt the given data using advanced cryptography techniques."""
    salt = await loop.run_in_executor(None, os.urandom, 16)
    bytes_data = await loop.run_in_executor(None, bytes, data, const.ENCODING)
    compressed = await loop.run_in_executor(None, zlib.compress, bytes_data)
    crc = await loop.run_in_executor(None, zlib.crc32, compressed)
    packed_crc = await loop.run_in_executor(None, struct.pack, '!I', crc)
    key = await _get_key_async(salt)
    f = await loop.run_in_executor(None, cryptography.fernet.Fernet, key)
    encoded = await loop.run_in_executor(
        None,
        f.encrypt,
        packed_crc + compressed
    )
    encrypted = await loop.run_in_executor(
        None,
        base64.urlsafe_b64decode,
        encoded
    )
    msg = salt + encrypted

    url_encoded = await loop.run_in_executor(
        None,
        base64.urlsafe_b64encode,
        msg
    )
    return await loop.run_in_executor(None, str, url_encoded, 'utf8')


def encrypt_sync(data: str)-> str:
    """Encrypt the given data using advanced cryptography techniques."""
    salt = os.urandom(16)
    bytes_data = bytes(data, const.ENCODING)
    compressed = zlib.compress(bytes_data)
    crc = zlib.crc32(compressed)
    packed_crc = struct.pack('!I', crc)
    key = _get_key_sync(salt)
    f = cryptography.fernet.Fernet(key)
    encoded = f.encrypt(packed_crc + compressed)
    encrypted = base64.urlsafe_b64decode(encoded)
    msg = salt + encrypted

    url_encoded = base64.urlsafe_b64encode(msg)
    return str(url_encoded, 'utf8')


@inject_loop
async def decrypt_async(
    data: str,
    *,
    loop: 'asyncio.AbstractEventLoop'
)-> str:
    """Decrypt the given data using advanced cryptography techniques."""
    decoded = await loop.run_in_executor(None, base64.urlsafe_b64decode, data)
    salt, encrypted = decoded[:16], decoded[16:]
    encoded = await loop.run_in_executor(
        None,
        base64.urlsafe_b64encode,
        encrypted
    )
    key = await _get_key_async(salt)
    f = await loop.run_in_executor(None, cryptography.fernet.Fernet, key)
    decrypted = await loop.run_in_executor(None, f.decrypt, encoded)
    packed_crc, compressed = decrypted[:4], decrypted[4:]

    crc, *__ = await loop.run_in_executor(
        None,
        struct.unpack,
        '!I',
        packed_crc
    )

    if crc != await loop.run_in_executor(None, zlib.crc32, compressed):
        raise ValueError('Unable to decrypt string.')

    decompressed = await loop.run_in_executor(
        None,
        zlib.decompress,
        compressed
    )
    return await loop.run_in_executor(None, str, decompressed, const.ENCODING)


def decrypt_sync(data: str)-> str:
    """Decrypt the given data using advanced cryptography techniques."""
    decoded = base64.urlsafe_b64decode(data)
    salt, encrypted = decoded[:16], decoded[16:]
    encoded = base64.urlsafe_b64encode(encrypted)
    key = _get_key_sync(salt)
    f = cryptography.fernet.Fernet(key)
    decrypted = f.decrypt(encoded)
    packed_crc, compressed = decrypted[:4], decrypted[4:]

    crc, *__ = struct.unpack('!I', packed_crc)

    if crc != zlib.crc32(compressed):
        raise ValueError('Unable to decrypt string.')

    decompressed = zlib.decompress(compressed)
    return str(decompressed, const.ENCODING)
