__all__ = ("AES",)

import os
import cryptography.hazmat.primitives.ciphers
import cryptography.hazmat.backends

_backend = cryptography.hazmat.backends.default_backend()
_aes = cryptography.hazmat.primitives.ciphers.algorithms.AES
_cipher = cryptography.hazmat.primitives.ciphers.Cipher
_ctrmode = cryptography.hazmat.primitives.ciphers.modes.CTR
_gcmmode = cryptography.hazmat.primitives.ciphers.modes.GCM

class AES(object):

    key_sizes = [k//8 for k in sorted(_aes.key_sizes)]
    block_size = _aes.block_size//8

    @staticmethod
    def KeyGen(size_bytes):
        assert size_bytes in AES.key_sizes
        return os.urandom(size_bytes)

    @staticmethod
    def CTREnc(key, plaintext):
        iv = os.urandom(AES.block_size)
        cipher = _cipher(_aes(key), _ctrmode(iv), backend=_backend).encryptor()
        return iv + cipher.update(plaintext) + cipher.finalize()

    @staticmethod
    def CTRDec(key, ciphertext):
        iv = ciphertext[:AES.block_size]
        cipher = _cipher(_aes(key), _ctrmode(iv), backend=_backend).decryptor()
        return cipher.update(ciphertext[AES.block_size:]) + \
               cipher.finalize()

    @staticmethod
    def GCMEnc(key, plaintext):
        iv = os.urandom(AES.block_size)
        cipher = _cipher(_aes(key), _gcmmode(iv), backend=_backend).encryptor()
        return iv + cipher.update(plaintext) + cipher.finalize() + cipher.tag

    @staticmethod
    def GCMDec(key, ciphertext):
        iv = ciphertext[:AES.block_size]
        tag = ciphertext[-AES.block_size:]
        cipher = _cipher(_aes(key), _gcmmode(iv, tag), backend=_backend).decryptor()
        return cipher.update(ciphertext[AES.block_size:-AES.block_size]) + \
               cipher.finalize()
