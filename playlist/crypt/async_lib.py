"""
Module containing asynchronous cryptography functions used in the gpm-playlist.

**********
Module API
**********

.. autosummary::
    :nosignatures:

    encrypt
    decrypt
"""
__all__ = (
    'encrypt',
    'decrypt',
)

import asyncio  # NOQA
import base64
import functools
import os
import struct
import zlib

import cryptography
import cryptography.fernet
import cryptography.hazmat.primitives
import cryptography.hazmat.primitives.kdf.pbkdf2

from playlist.core import const, lib


@lib.inject_loop
async def get_key(
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


@lib.inject_loop
async def encrypt(
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
    key = await get_key(salt)
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


@lib.inject_loop
async def decrypt(
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
    key = await get_key(salt)
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
