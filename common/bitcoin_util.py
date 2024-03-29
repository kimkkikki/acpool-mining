import struct
import binascii
from common.hash_util import double_sha


def deser_string(f):
    nit = struct.unpack("<B", f.read(1))[0]
    if nit == 253:
        nit = struct.unpack("<H", f.read(2))[0]
    elif nit == 254:
        nit = struct.unpack("<I", f.read(4))[0]
    elif nit == 255:
        nit = struct.unpack("<Q", f.read(8))[0]
    return f.read(nit)


def ser_string(s):
    if len(s) < 253:
        return chr(len(s)).encode() + s
    elif len(s) < 0x10000:
        return chr(253).encode() + struct.pack("<H", len(s)).encode() + s
    elif len(s) < 0x100000000:
        return chr(254).encode() + struct.pack("<I", len(s)).encode() + s
    return chr(255).encode() + struct.pack("<Q", len(s)).encode() + s


def deser_uint256(f):
    r = 0
    for i in range(8):
        t = struct.unpack("<I", f.read(4))[0]
        r += t << (i * 32)
    return r


def ser_uint256(u):
    rs = b""
    for i in range(8):
        rs += struct.pack("<I", u & 0xFFFFFFFF)
        u >>= 32
    return rs


def uint256_from_str(s):
    r = 0
    t = struct.unpack("<IIIIIIII", s[:32])
    for i in range(8):
        r += t[i] << (i * 32)
    return r


def uint256_from_str_be(s):
    r = 0
    t = struct.unpack(">IIIIIIII", s[:32])
    for i in range(8):
        r += t[i] << (i * 32)
    return r


def uint256_from_compact(c):
    nbytes = (c >> 24) & 0xFF
    v = (c & 0xFFFFFF) << (8 * (nbytes - 3))
    return v


def deser_vector(f, c):
    nit = struct.unpack("<B", f.read(1))[0]
    if nit == 253:
        nit = struct.unpack("<H", f.read(2))[0]
    elif nit == 254:
        nit = struct.unpack("<I", f.read(4))[0]
    elif nit == 255:
        nit = struct.unpack("<Q", f.read(8))[0]
    r = []
    for i in range(nit):
        t = c()
        t.deserialize(f)
        r.append(t)
    return r


def ser_vector(l):
    if len(l) < 253:
        r = chr(len(l)).encode()
    elif len(l) < 0x10000:
        r = chr(253).encode() + struct.pack("<H", len(l)).encode()
    elif len(l) < 0x100000000:
        r = chr(254).encode() + struct.pack("<I", len(l)).encode()
    else:
        r = chr(255).encode() + struct.pack("<Q", len(l)).encode()
    for i in l:
        r += i.serialize()
    return r


def deser_uint256_vector(f):
    nit = struct.unpack("<B", f.read(1))[0]
    if nit == 253:
        nit = struct.unpack("<H", f.read(2))[0]
    elif nit == 254:
        nit = struct.unpack("<I", f.read(4))[0]
    elif nit == 255:
        nit = struct.unpack("<Q", f.read(8))[0]
    r = []
    for i in range(nit):
        t = deser_uint256(f)
        r.append(t)
    return r


def ser_uint256_vector(l):
    if len(l) < 253:
        r = chr(len(l))
    elif len(l) < 0x10000:
        r = chr(253) + struct.pack("<H", len(l))
    elif len(l) < 0x100000000:
        r = chr(254) + struct.pack("<I", len(l))
    else:
        r = chr(255) + struct.pack("<Q", len(l))
    for i in l:
        r += ser_uint256(i)
    return r


__b58chars = '123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz'
__b58base = len(__b58chars)


def b58decode(v, length):
    """ decode v into a string of len bytes
    """
    long_value = 0
    for (i, c) in enumerate(v[::-1]):
        long_value += __b58chars.find(c) * (__b58base**i)

    result = ''
    while long_value >= 256:
        div, mod = divmod(long_value, 256)
        result = chr(mod) + result
        long_value = div
    result = chr(long_value) + result

    nPad = 0
    for c in v:
        if c == __b58chars[0]:
            nPad += 1
        else:
            break

    result = chr(0) * nPad + result
    if length is not None and len(result) != length:
        return None

    return result


def b58encode(value):
    """ encode integer 'value' as a base58 string; returns string
    """
    encoded = ''
    while value >= __b58base:
        div, mod = divmod(value, __b58base)
        encoded = __b58chars[mod] + encoded  # add to left
        value = div
    encoded = __b58chars[value] + encoded  # most significant remainder
    return encoded


def reverse_hash(h):
    # This only revert byte order, nothing more
    if len(h) != 64:
        raise Exception('hash must have 64 hexa chars')

    return b''.join([h[56 - i:64 - i] for i in range(0, 64, 8)])


def bits_to_target(bits):
    return struct.unpack('<L', bits[:3] + b'\0')[0] * 2**(8 * (int(bits[3], 16) - 3))


def address_to_pubkeyhash(addr):
    try:
        addr = b58decode(addr, 26)
    except Exception:
        return None

    if addr is None:
        return None

    ver = addr[0]
    cksumA = addr[-4:]
    cksumB = double_sha(addr[:-4])[:4]

    if cksumA != cksumB:
        return None

    return (ver, addr[1:-4])


def ser_uint256_be(u):
    '''ser_uint256 to big endian'''
    rs = b""
    for i in range(8):
        rs += struct.pack(">I", u & 0xFFFFFFFF)
        u >>= 32
    return rs


def deser_uint256_be(f):
    r = 0
    for i in range(8):
        t = struct.unpack(">I", f.read(4))[0]
        r += t << (i * 32)
    return r


def ser_number(n):
    # For encoding nHeight into coinbase
    s = bytearray(b'\1')
    while n > 127:
        s[0] += 1
        s.append(n % 256)
        n //= 256
    s.append(n)
    return bytes(s)


def script_to_address(addr):
    d = address_to_pubkeyhash(addr)
    if not d:
        raise ValueError('invalid address')
    (ver, pubkeyhash) = d
    return b'\x76\xa9\x14' + pubkeyhash + b'\x88\xac'


def script_to_pubkey(key):
    if len(key) == 66:
        key = binascii.unhexlify(key)
    if len(key) != 33:
        raise Exception('Invalid Address')
    return b'\x21' + key + b'\xac'


class MerkleTree:
    def __init__(self, data, detailed=False):
        self.data = data
        self.recalculate(detailed)
        self._hash_steps = None

    def recalculate(self, detailed=False):
        L = self.data
        steps = []
        if detailed:
            detail = []
            PreL = []
            StartL = 0
        else:
            detail = None
            PreL = [None]
            StartL = 2
        Ll = len(L)
        if detailed or Ll > 1:
            while True:
                if detailed:
                    detail += L
                if Ll == 1:
                    break
                steps.append(L[1])
                if Ll % 2:
                    L += [L[-1]]
                L = PreL + [double_sha(L[i] + L[i + 1]) for i in range(StartL, Ll, 2)]
                Ll = len(L)
        self._steps = steps
        self.detail = detail

    def hash_steps(self):
        if self._hash_steps is None:
            self._hash_steps = double_sha(b''.join(self._steps))
        return self._hash_steps

    def withFirst(self, f):
        steps = self._steps
        for s in steps:
            f = double_sha(f + s)
        return f

    def merkleRoot(self):
        return self.withFirst(self.data[0])
