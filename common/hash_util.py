import struct
import base58
import binascii
from hashlib import sha256
import os
import sha3


def double_sha(b):
    return sha256(sha256(b).digest()).digest()


def sha(b):
    return sha256(b).digest()


def hex_to_reverse_hash(_hex):
    return binascii.hexlify(reverse_bytes(double_sha(binascii.unhexlify(_hex))))


def bytes_to_reverse_hash(_bytes):
    return binascii.hexlify(reverse_bytes(double_sha(_bytes)))


def hex_to_reverse_hex(_hex) -> str:
    return binascii.hexlify(reverse_bytes(binascii.unhexlify(_hex))).decode()


def bytes_to_reverse_hex(_bytes):
    return binascii.hexlify(reverse_bytes(_bytes))


def merkle_root(hashes: list):
    if len(hashes) == 1:
        return hashes[0]

    reverse_hashes = []
    for _hash in hashes:
        reverse_hashes.append(reverse_bytes(binascii.unhexlify(_hash)))

    _merkle_root = None
    while _merkle_root is None:
        tmp_tree = []

        if len(reverse_hashes) % 2 == 1:
            reverse_hashes.append(reverse_hashes[len(reverse_hashes) - 1])

        for i in range(len(reverse_hashes)):
            if i % 2 == 0:
                tmp_tree.append(double_sha(reverse_hashes[i] + reverse_hashes[i + 1]))

        if len(tmp_tree) == 1:
            _merkle_root = tmp_tree[0]
        else:
            reverse_hashes = tmp_tree

    _merkle_root = binascii.hexlify(reverse_bytes(_merkle_root))

    return _merkle_root


def reverse_bytes(b: bytes):
    _list = list(b)
    _list.reverse()
    return bytes(_list)


def uint256_from_str(s):
    r = 0
    t = struct.unpack("<IIIIIIII", s[:32])
    for i in range(8):
        r += t[i] << (i * 32)
    return r


def address_to_pubkeyhash(addr):
    try:
        addr = base58.b58decode(addr.encode())
    except Exception:
        return None

    if addr is None:
        return None

    ver = addr[0]
    check_sum_a = addr[-4:]

    if os.getenv("COIN_ALGORITHM") == 'keccak':
        check_sum_b = sha3.keccak_256(addr[:-4]).digest()[:4]
    else:
        check_sum_b = double_sha(addr[:-4])[:4]

    if check_sum_a != check_sum_b:
        return None

    # TODO: modify [1:-4] to [2:-4] 왜이런지는 모르겠음
    if os.getenv("COIN_TYPE") == 'zcash':
        return ver, addr[2:-4]
    else:
        return ver, addr[1:-4]


def var_int(txs):
    if len(txs) < 253:
        r = chr(len(txs))
    elif len(txs) < 0x10000:
        r = chr(253) + struct.pack("<H", len(txs))
    elif len(txs) < 0x100000000:
        r = chr(254) + struct.pack("<I", len(txs))
    else:
        r = chr(255) + struct.pack("<Q", len(txs))
    return r.encode()
