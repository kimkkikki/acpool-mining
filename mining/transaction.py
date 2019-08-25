import struct
import binascii
from common import hash_util
import os


class Transaction(object):
    DEFAULT_SEQUENCE = 0xffffffff
    EMPTY_SCRIPT = ''
    EMPTY_WITNESS = []

    def __init__(self, curtime=0):
        if os.getenv("COIN") == 'zcash' and os.getenv("CASH_NET_TYPE") == 'testnet':
            self.version = 3
            self.group_id = 0x03c48270
        elif os.getenv("COIN") in ['xchange']:
            self.version = 2
        else:
            self.version = 1
        self.locktime = 0
        self.curtime = curtime
        self.ins = []
        self.outs = []
        self.joinsplits = []

    def add_input(self, _hash, _index, _sequence=DEFAULT_SEQUENCE, _script_sig=EMPTY_SCRIPT):
        if self.version == 2 and _sequence == 4294967295:
            _sequence = 0

        self.ins.append({'hash': _hash, 'index': _index, 'script': _script_sig, 'sequence': _sequence, 'witness': self.EMPTY_WITNESS})

    def add_output(self, script_pub_key, value):
        self.outs.append({'script': script_pub_key, 'value': value})

    @staticmethod
    def set_bit(v, index, x):
        """Set the index:th bit of v to 1 if x is truthy, else to 0, and return the new value."""
        mask = 1 << index  # Compute mask, an integer with just bit 'index' set.
        v &= ~mask  # Clear the bit indicated by the mask (if x is False)
        if x:
            v |= mask  # If x was True, set the bit indicated by the mask.
        return v  # Return the result, we're done.

    def to_hex(self):
        r = b''

        if os.getenv("COIN") == 'zcash' and os.getenv("CASH_NET_TYPE") == 'testnet':
            version = self.set_bit(self.version, 31, 1)
            r += struct.pack("<I", version)
            r += struct.pack('<I', self.group_id)
        else:
            r += struct.pack("<I", self.version)
            if os.getenv("COIN") == 'verge':
                r += binascii.unhexlify(self.curtime)

        r += hash_util.var_int(self.ins)
        for _in in self.ins:
            r += _in['hash']
            r += struct.pack("<I", _in['index'])
            r += hash_util.var_int(_in['script'])
            r += _in['script']
            r += struct.pack("<I", _in['sequence'])

        r += hash_util.var_int(self.outs)
        for _out in self.outs:
            r += struct.pack("<Q", int(_out['value']))
            r += hash_util.var_int(_out['script'])
            r += _out['script']

        r += struct.pack("<I", self.locktime)

        if os.getenv("COIN") == 'zcash' and os.getenv("CASH_NET_TYPE") == 'testnet':
            r += binascii.unhexlify('0000000000')

        return r
