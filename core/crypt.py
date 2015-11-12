import base64
import contextlib
import struct
import zlib

import Crypto
import Crypto.Random

try:
    from playlist import boot

except ImportError:
    pass


def _get_key():
    try:
        return _get_key.key

    except AttributeError:
        sha = Crypto.Hash.SHA256.new()
        try:
            sha.update(boot.get_app_config().secret_key)

        except (NameError, TypeError, AttributeError):
            sha.update(__name__)

        _get_key.key = sha.digest()
        return _get_key.key


def encrypt(data):
    iv = Crypto.Random.new().read(Crypto.Cipher.AES.block_size)
    cipher = Crypto.Cipher.AES.new(_get_key(), Crypto.Cipher.AES.MODE_CFB, iv)
    compressed = zlib.compress(data)
    crc = zlib.crc32(compressed)
    packed_crc = struct.pack('>i', crc)
    encrypted = cipher.encrypt(''.join((packed_crc, compressed)))
    msg = ''.join((iv, encrypted))
    return base64.b64encode(msg)


def decrypt(data):
    decoded = base64.b64decode(data)
    iv, encrypted = decoded[:16], decoded[16:]
    cipher = Crypto.Cipher.AES.new(_get_key(), Crypto.Cipher.AES.MODE_CFB, iv)
    decrypted = cipher.decrypt(encrypted)
    packed_crc, compressed = decrypted[:4], decrypted[4:]
    (crc, ) = struct.unpack('>i', packed_crc)
    if crc != zlib.crc32(compressed):
        raise ValueError('Unable to decrypt string.')

    return zlib.decompress(compressed)