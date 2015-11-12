import base64
import struct
import zlib

import Crypto
import Crypto.Random

def _get_key():
    sha = Crypto.Hash.SHA256.new()
    sha.update(__name__)
    return sha.digest()
    
def encrypt(data):
    iv = Crypto.Random.new().read(Crypto.Cipher.AES.block_size)
    cipher = Crypto.Cipher.AES.new(_get_key(), Crypto.Cipher.AES.MODE_CFB, iv)
    compressed = zlib.compress(data)
    crc = zlib.crc32(compressed)
    packed_crc = struct.pack('!I', crc)
    encrypted = cipher.encrypt(''.join((packed_crc, compressed)))
    msg = ''.join((iv, encrypted))
    return base64.b64encode(msg)
    
def decrypt(data):
    decoded = base64.b64decode(data)
    iv, encrypted = decoded[:16], decoded[16:]
    cipher = Crypto.Cipher.AES.new(_get_key(), Crypto.Cipher.AES.MODE_CFB, iv)
    decrypted = cipher.decrypt(encrypted)
    packed_crc, compressed = decrypted[:4], decrypted[4:]
    (crc, ) = struct.unpack('!I', packed_crc)
    if crc != zlib.crc32(compressed):
        raise ValueError('Unable to decrypt string.')
        
    return zlib.decompress(compressed)