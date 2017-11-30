"""
Module containing synchronous cryptography functions used in the gpm-playlist.

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

import base64
import os
import struct
import zlib

import cryptography
import cryptography.fernet
import cryptography.hazmat.primitives
import cryptography.hazmat.primitives.kdf.pbkdf2

from playlist.core import const


def get_key(salt: bytes) -> bytes:
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


def encrypt(data: str)-> str:
    """Encrypt the given data using advanced cryptography techniques."""
    salt = os.urandom(16)
    bytes_data = bytes(data, const.ENCODING)
    compressed = zlib.compress(bytes_data)
    crc = zlib.crc32(compressed)
    packed_crc = struct.pack('!I', crc)
    key = get_key(salt)
    f = cryptography.fernet.Fernet(key)
    encoded = f.encrypt(packed_crc + compressed)
    encrypted = base64.urlsafe_b64decode(encoded)
    msg = salt + encrypted

    url_encoded = base64.urlsafe_b64encode(msg)
    return str(url_encoded, 'utf8')


def decrypt(data: str)-> str:
    """Decrypt the given data using advanced cryptography techniques."""
    decoded = base64.urlsafe_b64decode(data)
    salt, encrypted = decoded[:16], decoded[16:]
    encoded = base64.urlsafe_b64encode(encrypted)
    key = get_key(salt)
    f = cryptography.fernet.Fernet(key)
    decrypted = f.decrypt(encoded)
    packed_crc, compressed = decrypted[:4], decrypted[4:]

    crc, *__ = struct.unpack('!I', packed_crc)

    if crc != zlib.crc32(compressed):
        raise ValueError('Unable to decrypt string.')

    decompressed = zlib.decompress(compressed)
    return str(decompressed, const.ENCODING)
