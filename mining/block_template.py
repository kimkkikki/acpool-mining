from common.logger import get_logger
from common import hash_util, bitcoin_util
from mining.transaction import Transaction
from mining.interfaces import Interfaces
import os
import struct
import binascii
import math

logger = get_logger(__name__)


class BlockTemplate(object):
    def __init__(self, pool_address):
        logger.debug('Start Initialize Block Template')

        self.prev_hash = None
        self.prev_hash_reverse_hex = ''
        self.merkle_root = ''
        self.merkle_root_reverse_hex = ''
        self.version = 1
        self.n_bits = ''
        self.n_bits_reverse_hex = ''

        self.curtime = ''

        self.target = ''
        self.difficulty = 0.0
        self.block_height = 0

        self.subsidy = False
        self.block_reward = 0.0
        self.fee = 0.0
        self.pool_reward = 0.0

        self.tx_count = 0
        self.transactions = []
        self.coinbase_tx = b''
        self.coinbase_tx_hash = ''
        self.coinbase_aux = b'https://acpool.me'

        self.extranonce_placeholder = b'f000000ff111111f'
        self.merkle_branch = []
        self.pool_address = hash_util.address_to_pubkeyhash(pool_address)[1]

        self.with_pos = False
        self.pos_payee = ''
        self.pos_amount = 0

    def merkle_update(self, data, notify: bool):
        is_merkle_change = False
        self.transactions = data['transactions']

        self.fee = 0
        for tx in self.transactions:
            self.fee += tx['fee']

        self.tx_count = len(self.transactions) + 1

        # Zcash!!
        if 'coinbasetxn' in data and os.getenv("COIN") == 'komodo':
            coinbasetxn = data['coinbasetxn']
            self.coinbase_tx = binascii.unhexlify(coinbasetxn['data'])
            self.coinbase_tx_hash = hash_util.bytes_to_reverse_hash(self.coinbase_tx)
            if os.getenv("COIN") == 'zcash':
                pool_reward = round(float(self.block_reward) * 0.8)
            else:
                pool_reward = round(float(self.block_reward))
            self.pool_reward = pool_reward + self.fee
        else:
            self.create_coinbase_transaction()

        if os.getenv("COIN_TYPE") == 'bitcoin':
            tx_hashes = [None] + [bitcoin_util.ser_uint256(int(t['hash'], 16)) for t in self.transactions]
            merkle_tree = bitcoin_util.MerkleTree(tx_hashes)
            tmp_merkle_branch = [binascii.hexlify(x).decode() for x in merkle_tree._steps]

            if self.merkle_branch != tmp_merkle_branch:
                self.merkle_branch = tmp_merkle_branch
                is_merkle_change = True

        elif os.getenv("COIN_TYPE") == 'zcash':
            tx_hashes = [self.coinbase_tx_hash] + [h['hash'] for h in self.transactions]
            tmp_merkle_root = hash_util.merkle_root(tx_hashes)

            if self.merkle_root != tmp_merkle_root:
                self.merkle_root = tmp_merkle_root
                self.merkle_root_reverse_hex = hash_util.hex_to_reverse_hex(self.merkle_root)
                is_merkle_change = True

        if Interfaces.stratum_handler is not None:
            if notify:
                logger.debug('Found New Block, notify all')
                Interfaces.stratum_handler.notify_all()
            elif is_merkle_change:
                logger.info('Merkle Changed, merkle length : %d' % len(self.transactions))
                Interfaces.stratum_handler.notify_all()

    def block_update(self, data):
        self.version = data['version']
        self.target = data['target']

        target = int(data['target'], 16)
        if target == 0:
            target = os.getenv("POW_LIMIT")
            logger.error('Target is Zero, change to 1')

        self.difficulty = os.getenv("POW_LIMIT") / target
        logger.info('Current difficulty is %f' % self.difficulty)

        self.curtime = binascii.hexlify(struct.pack("<I", data['curtime'])).decode()
        self.n_bits = data['bits']

        self.prev_hash = data['previousblockhash']
        self.block_height = data['height']

        self.prev_hash_reverse_hex = hash_util.hex_to_reverse_hex(data['previousblockhash'])
        self.n_bits_reverse_hex = hash_util.hex_to_reverse_hex(data['bits'])

        if not self.subsidy:
            self.block_reward = data['coinbasevalue']

        if os.getenv("COIN") == 'smartcash':
            self.pos_payee = data['smartnode']['payee']
            self.pos_amount = data['smartnode']['amount']
            self.with_pos = True

        elif os.getenv("COIN") in ['lux', 'xchange', 'absolute']:
            self.pos_payee = data['masternode']['payee']
            self.pos_amount = data['masternode']['amount']
            self.with_pos = True
            self.block_reward = self.block_reward - self.pos_amount

        elif os.getenv("COIN") in ['galactrum']:
            self.pos_payee = data['masternode']['payee']
            self.pos_amount = data['masternode']['amount']
            self.with_pos = True
            self.block_reward = self.block_reward

        elif os.getenv("COIN") in ['straks', 'bitsend', 'methuselah']:
            self.pos_payee = data['payee']
            self.pos_amount = data['payee_amount']
            self.with_pos = True
            self.block_reward = self.block_reward - self.pos_amount
            if os.getenv("COIN") == 'straks':
                self.founders_reward = data['coinbasetxn']['treasuryreward']
                self.block_reward = self.block_reward - self.founders_reward

        if 'coinbaseaux' in data and 'flags' in data['coinbaseaux'] and data['coinbaseaux']['flags'] != '':
            self.coinbase_aux = binascii.unhexlify(data['coinbaseaux']['flags'])

    def create_coinbase_transaction(self):
        tx = Transaction(self.curtime)

        block_height_serial = format(self.block_height, 'x')
        if abs(len(block_height_serial) % 2) == 1:
            block_height_serial = '0' + block_height_serial

        height = math.ceil((len(bin(self.block_height << 1)) - 2) / 8)
        length_diff = len(block_height_serial) / 2 - height

        for i in range(int(length_diff)):
            block_height_serial += '00'

        length = '0' + str(height)

        serialize_block_height = binascii.unhexlify(length)
        serialize_block_height += binascii.unhexlify(hash_util.hex_to_reverse_hex(block_height_serial))
        serialize_block_height += binascii.unhexlify('00')

        if os.getenv("COIN_TYPE") == 'bitcoin':
            serialize_block_height += binascii.unhexlify(self.extranonce_placeholder)

        tx.add_input(binascii.unhexlify('0000000000000000000000000000000000000000000000000000000000000000'), 4294967295, 4294967295, serialize_block_height + self.coinbase_aux)

        if os.getenv("COIN") == 'zcash':
            pool_reward = round(float(self.block_reward) * 0.8)
        elif os.getenv("COIN") == 'bitcoinz':
            pool_reward = round(float(self.block_reward) * 0.999)
        else:
            pool_reward = round(float(self.block_reward))

        if os.getenv("COIN_TYPE") == 'zcash':
            pool_reward += self.fee

        self.pool_reward = pool_reward
        if self.with_pos:
            tx.add_output(b'\x76\xa9\x14' + hash_util.address_to_pubkeyhash(self.pos_payee)[1] + b'\x88\xac', self.pos_amount)

        if os.getenv("COIN") in ['vertcoin', 'shield', 'feathercoin']:
            tx.add_output(b'\xa9\x14' + self.pool_address + b'\x87', pool_reward)
        else:
            tx.add_output(b'\x76\xa9\x14' + self.pool_address + b'\x88\xac', pool_reward)

        if os.getenv("COIN") == 'zcash':
            founders_index = int(math.floor(self.block_height / 17709))
            founders_address = os.getenv("FOUNDERS_REWARD")[founders_index]
            founders_address_hash = hash_util.address_to_pubkeyhash(founders_address)[1]
            founders_reward = round(float(self.block_reward) * 0.2)
            tx.add_output(b'\xa9\x14' + founders_address_hash + b'\x87', founders_reward)

        elif os.getenv("COIN") == 'smartcash':
            block_rotation = int(self.block_height - 85 * int(self.block_height / 85))
            if 0 <= block_rotation <= 7:
                founders_index = 0
            elif 8 <= block_rotation <= 15:
                founders_index = 1
            elif 16 <= block_rotation <= 23:
                founders_index = 2
            elif 24 <= block_rotation <= 38:
                founders_index = 3
            else:
                founders_index = 4

            smart_hive_amount = (math.floor(0.5 + ((5000 * 143500) / (self.block_height + 1))) * 100000000) * 0.85
            smart_hive = hash_util.address_to_pubkeyhash(os.getenv("FOUNDERS_REWARD")[founders_index])[1]
            tx.add_output(b'\x76\xa9\x14' + smart_hive + b'\x88\xac', smart_hive_amount)

        elif os.getenv("COIN") == 'straks':
            founders_address = os.getenv("FOUNDERS_REWARD")[self.block_height % 4]
            founders_address_pubkey = hash_util.address_to_pubkeyhash(founders_address)[1]
            tx.add_output(b'\xa9\x14' + founders_address_pubkey + b'\x87', self.founders_reward)

        elif os.getenv("COIN") == 'bitcoinz':
            donation_reward = round(float(self.block_reward) * 0.001)
            tx.add_output(b'\x76\xa9\x14' + hash_util.address_to_pubkeyhash('t1fHHnAXxoPWGY77sG5Zw2sFfGUTpW6BcSZ')[1] + b'\x88\xac', donation_reward)

        self.coinbase_tx = tx.to_hex()
        self.coinbase_tx_hash = hash_util.bytes_to_reverse_hash(self.coinbase_tx)

    def serialize_block_header(self, n_time: bytes, nonce: bytes, merkle_root=None):
        header = struct.pack("<I", self.version)
        header += binascii.unhexlify(self.prev_hash_reverse_hex)

        if merkle_root is not None:
            header += binascii.unhexlify(merkle_root)
        else:
            header += binascii.unhexlify(self.merkle_root_reverse_hex)

        if os.getenv("COIN_TYPE") == 'zcash':
            header += binascii.unhexlify(b'0000000000000000000000000000000000000000000000000000000000000000')

        header += binascii.unhexlify(n_time)
        header += binascii.unhexlify(self.n_bits_reverse_hex)
        header += binascii.unhexlify(nonce)

        return header

    def serialize_block(self, header, soln=None, coinbase=None):
        tx_count = format(self.tx_count, 'x')

        if abs(len(tx_count) % 2) == 1:
            tx_count = '0' + tx_count

        if self.tx_count <= 0x7f:
            var_int = binascii.unhexlify(tx_count)
        else:
            var_int = binascii.unhexlify('FD') + binascii.unhexlify(tx_count)

        if soln is not None:
            buf = header + soln + var_int + self.coinbase_tx
        elif coinbase is not None:
            buf = header + var_int + coinbase
        else:
            raise Exception('soln or coinbase required')

        for transaction in self.transactions:
            buf += binascii.unhexlify(transaction['data'])

        return buf
