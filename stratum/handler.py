from mining.interfaces import Interfaces
from common.hash_util import double_sha, uint256_from_str
from common import hash_util, bitcoin_util
from common.logger import get_logger
import binascii
import struct
import os

logger = get_logger(__name__)


class ACPoolHandler(object):
    def __init__(self):
        logger.debug('Initialize Stratum Handler')
        self.coin_rpc = Interfaces.coin_rpc
        self.block_template = Interfaces.block_template
        self.job_manager = Interfaces.job_manager
        self.database_ref = Interfaces.database
        self.connections = set()
        self.user_diffs = {}

    def disconnect(self, connection_ref):
        self.database_ref.disconnected_worker(connection_ref.username, connection_ref.worker_name, connection_ref.host)
        if connection_ref in self.connections:
            self.connections.remove(connection_ref)

    def handle_event(self, connection_ref, json_message: dict):
        msg_id = json_message.get('id', 0)
        msg_method = json_message.get('method')
        msg_params = json_message.get('params')

        result = None
        if msg_method == 'mining.subscribe':
            result = self.subscribe(connection_ref, msg_id, msg_params)
        elif msg_method == 'mining.authorize':
            result = self.authorize(connection_ref, msg_id, msg_params)
        elif msg_method == 'mining.extranonce.subscribe':
            result = self.extranonce_subscribe(msg_id)
        elif msg_method == 'mining.submit':
            result = self.submit(connection_ref, msg_id, msg_params)
        elif msg_method == 'web.validate.address':
            result = self.validate_address(msg_id, msg_params)
        elif msg_method == 'web.payout':
            result = self.payout(msg_id, msg_params)
        elif msg_method == 'web.status':
            result = self.status(msg_id)

        return result

    def set_target(self, connection_ref):
        # TODO: Var Diff 고려
        diff = self.user_diffs[connection_ref.username]

        if os.getenv("COIN_TYPE") == 'zcash':
            target_diff = format(int(os.getenv("POW_LIMIT") / diff), 'x')
            for i in range(64 - len(target_diff)):
                target_diff = '0' + target_diff
            connection_ref.send_message({'id': None, 'method': 'mining.set_target', 'params': [target_diff]})

        elif os.getenv("COIN_TYPE") == 'bitcoin':
            if os.getenv("COIN_ALGORITHM") in ['yescrypt', 'neoscrypt']:
                target_diff = diff * 65536
            elif os.getenv("COIN") == 'bitcoin':
                target_diff = diff
            else:
                target_diff = diff * 256
            connection_ref.send_message({'id': None, 'method': 'mining.set_difficulty', 'params': [target_diff]})

    def notify(self, connection_ref, first):
        # TODO: Notify 시 무조건 Target Setting 에서 적절한 Target Setting 으로 변경 필요
        if first:
            self.set_target(connection_ref)
        session_id = connection_ref.get_session()
        job_id = self.job_manager.get_new_job_id(session_id, self.block_template)

        if os.getenv("COIN_TYPE") == 'zcash':
            version = binascii.hexlify(struct.pack("<I", self.block_template.version)).decode()
            prevhash = self.block_template.prev_hash_reverse_hex
            bits = self.block_template.n_bits_reverse_hex
            reserved = '0000000000000000000000000000000000000000000000000000000000000000'
            time = self.block_template.curtime
            merkle_root = self.block_template.merkle_root_reverse_hex
            if os.getenv("COIN_ALGORITHM") == 'zhash':
                if os.getenv("COIN") == 'bitcoin-gold':
                    pers = 'BgoldPoW'
                elif os.getenv("COIN") == 'bitcoinz':
                    pers = 'BitcoinZ'
                elif os.getenv("COIN") == 'classic-bitcoin':
                    pers = 'CbtcPoW'
                elif os.getenv("COIN") == 'zelcash':
                    pers = 'ZelProof'
                else:
                    raise Exception('invalid coin type')
                params = [job_id, version, prevhash, merkle_root, reserved, time, bits, True, False, pers]
            else:
                params = [job_id, version, prevhash, merkle_root, reserved, time, bits, True]
            connection_ref.send_message({'id': None, 'method': 'mining.notify', 'params': params})

        elif os.getenv("COIN_TYPE") == 'bitcoin':
            version = binascii.hexlify(struct.pack(">I", self.block_template.version)).decode()
            prevhash = bitcoin_util.reverse_hash(self.block_template.prev_hash.encode()).decode()
            coinbase = binascii.hexlify(self.block_template.coinbase_tx).split(self.block_template.extranonce_placeholder)
            merkle_branch = self.block_template.merkle_branch
            bits = self.block_template.n_bits
            time = hash_util.hex_to_reverse_hex(self.block_template.curtime)
            params = [job_id, prevhash, coinbase[0].decode(), coinbase[1].decode(), merkle_branch, version, bits, time, True]
            connection_ref.send_message({'id': None, 'method': 'mining.notify', 'params': params})

    def notify_all(self):
        for connection_ref in self.connections:
            self.notify(connection_ref, False)

        self.job_manager.clear_submits()

    def subscribe(self, connection_ref, _id, _params: list):
        session_id = connection_ref.get_session()
        nonce_1 = self.job_manager.get_new_nonce(session_id).decode()

        connection_ref.miner_program = _params[0]

        if os.getenv("COIN_TYPE") == 'zcash':
            return {'id': _id, 'result': (session_id, nonce_1), 'error': None}
        elif os.getenv("COIN_TYPE") == 'bitcoin':
            build_result = [['mining.notify', session_id], nonce_1, 4]
            return {'id': _id, 'result': build_result, 'error': None}

    def authorize(self, connection_ref, _id, _params):
        split_username = _params[0].strip().split('.')
        username = split_username[0]
        if len(split_username) == 2:
            worker_name = split_username[1]
        else:
            worker_name = 'default'

        if self.database_ref.get_user(username) is None:
            valid_result = self.coin_rpc.validate_address(username)
            if valid_result['isvalid']:
                self.database_ref.get_or_create_address_user(username)
            else:
                logger.info('Unknown user %s' % _params[0])
                return {'id': _id, 'result': False, 'error': None}

        if 'd=' in _params[1]:
            diff = float(_params[1].replace('d=', ''))
            self.user_diffs[username] = diff
        else:
            self.user_diffs[username] = float(os.getenv("POOL_DIFF"))

        connection_ref.worker_name = worker_name
        connection_ref.username = username

        logger.info('New worker Connected %s' % _params[0])

        self.database_ref.connected_worker(connection_ref.host, username, worker_name, connection_ref.miner_program)
        self.connections.add(connection_ref)
        return {'id': _id, 'result': True, 'error': None}

    @staticmethod
    def extranonce_subscribe(_id):
        return {'id': _id, 'result': True, 'error': None}

    def submit(self, connection_ref, _id, _params):
        # TODO: Job ID Check 구현해야함
        # TODO: Diff Check 해서 그냥 Share 기록 or Submit 구별 해야함
        # TODO: Share Result를 Database에 기록 해야함 - Database 는 Redis가 될듯
        session_id = connection_ref.get_session()

        _worker_name = _params[0]
        _split_worker_name = _worker_name.strip().split('.')
        username = _split_worker_name[0]
        if len(_split_worker_name) == 2:
            worker = _split_worker_name[1]
        else:
            worker = None
        _job_id = _params[1]

        _nonce_1 = self.job_manager.get_nonce_from_session_id(session_id)
        _block_template = self.job_manager.get_block_template(_job_id)

        if _block_template is None:
            logger.info('rejected share, worker : %s, reason : job not found' % _worker_name)
            return {'id': _id, 'result': False, 'error': [21, 'job not found']}

        if os.getenv("COIN_TYPE") == 'bitcoin':
            _nonce_2 = _params[2]
            _time = _params[3]
            _time_reverse = hash_util.hex_to_reverse_hex(_time)
            _nonce = _params[4]
            _nonce_reverse = hash_util.hex_to_reverse_hex(_nonce)

            if len(_nonce) != 8:
                logger.info('rejected share, worker : %s, reason : incorrect size of nonce' % _worker_name)
                return {'id': _id, 'result': False, 'error': [20, 'incorrect size of nonce']}

            coinbase = binascii.hexlify(_block_template.coinbase_tx).split(_block_template.extranonce_placeholder)
            serialized_coinbase = binascii.unhexlify(coinbase[0] + _nonce_1 + _nonce_2.encode() + coinbase[1])

            if os.getenv("COIN_ALGORITHM") == 'keccak':
                coinbase_hash = binascii.hexlify(hash_util.reverse_bytes(hash_util.sha(serialized_coinbase)))
            else:
                coinbase_hash = hash_util.bytes_to_reverse_hash(serialized_coinbase)

            tx_hashes = [coinbase_hash] + [h['hash'] for h in _block_template.transactions]
            merkle_root_reverse_hex = hash_util.hex_to_reverse_hex(hash_util.merkle_root(tx_hashes))

            # Header POW 종류별 구별 해야댐
            header = _block_template.serialize_block_header(_time_reverse, _nonce_reverse, merkle_root_reverse_hex)  # 80 bytes
            block_hex = _block_template.serialize_block(header, None, serialized_coinbase)
            if os.getenv("COIN_ALGORITHM") == 'lyra2rev2':
                import lyra2re2_hash
                header_hash = lyra2re2_hash.getPoWHash(header)
            elif os.getenv("COIN_ALGORITHM") == 'lyra2rev3':
                import lyra2re3_hash
                header_hash = lyra2re3_hash.getPoWHash(header)
            elif os.getenv("COIN_ALGORITHM") == 'keccak' or os.getenv("COIN_ALGORITHM") == 'keccakc':
                import sha3
                header_hash = sha3.keccak_256(header).digest()
            elif os.getenv("COIN_ALGORITHM") == 'x13-bcd':
                import x13bcd_hash
                header_hash = x13bcd_hash.getPoWHash(header)
            elif os.getenv("COIN_ALGORITHM") == 'neoscrypt':
                import neoscrypt
                header_hash = neoscrypt.getPoWHash(header)
            elif os.getenv("COIN_ALGORITHM") == 'yescrypt':
                import yescrypt_hash
                header_hash = yescrypt_hash.getHash(header, len(header))
            elif os.getenv("COIN_ALGORITHM") == 'xevan':
                import xevan_hash
                header_hash = xevan_hash.getPoWHash(header)
            elif os.getenv("COIN_ALGORITHM") == 'phi2':
                import phi2_hash
                header_hash = phi2_hash.getPoWHash(header)
            elif os.getenv("COIN_ALGORITHM") == 'x16r':
                import x16r_hash
                header_hash = x16r_hash.getPoWHash(header)
            elif os.getenv("COIN_ALGORITHM") == 'x16s':
                import x16s_hash
                header_hash = x16s_hash.getPoWHash(header)
            elif os.getenv("COIN_ALGORITHM") == 'timetravel10':
                import timetravel10_hash
                header_hash = timetravel10_hash.getPoWHash(header)
            else:
                header_hash = double_sha(header)

        elif os.getenv("COIN_TYPE") == 'zcash':
            _time = _params[2]
            _nonce_2 = _params[3]
            _soln = _params[4]

            _nonce = _nonce_1 + _nonce_2.encode()

            if len(_nonce) != 64:
                return {'id': _id, 'result': False, 'error': [20, 'incorrect size of nonce']}

            if os.getenv("COIN_ALGORITHM") == 'zhash' and len(_soln) != 202:
                return {'id': _id, 'result': False, 'error': [20, 'incorrect size of solution']}
            elif os.getenv("COIN_ALGORITHM") != 'zhash' and len(_soln) != 2694:
                return {'id': _id, 'result': False, 'error': [20, 'incorrect size of solution']}

            n_time_int = int(_time, 16)
            curtime_int = int(_block_template.curtime, 16)

            if n_time_int < curtime_int:
                return {'id': _id, 'result': False, 'error': [20, 'ntime out of range']}

            header = _block_template.serialize_block_header(_time.encode(), _nonce)  # 140 bytes

            header_soln = header + binascii.unhexlify(_soln)
            header_hash = double_sha(header_soln)

            block_hex = _block_template.serialize_block(header, binascii.unhexlify(_soln), None)
        else:
            raise Exception('invalid coin type')

        header_bignum = uint256_from_str(header_hash)

        share_diff = os.getenv("POW_LIMIT") / header_bignum
        logger.debug('share diff : {0:.8f}'.format(share_diff))

        diff = self.user_diffs[connection_ref.username]

        if share_diff < diff:
            # logger.debug('low difficulty share of %s' % share_diff)
            logger.info('rejected share, worker : %s, reason : low difficulty share' % _worker_name)
            self.database_ref.insert_accepted_share(username, worker, False, False, _block_template.block_height, share_diff, _block_template.pool_reward, diff)
            return {'id': _id, 'result': None, 'error': [23, 'low difficulty share of %s' % share_diff]}

        if not self.job_manager.register_submit(_nonce_1, _nonce_2, _nonce, _time):
            logger.info('rejected share, worker : %s, reason : duplicate share' % _worker_name)
            return {'id': _id, 'result': None, 'error': [22, 'duplicate share']}

        if share_diff >= _block_template.difficulty * 0.99:
            block_hash = binascii.hexlify(hash_util.reverse_bytes(header_hash)).decode()
            if os.getenv("COIN") in ['monacoin', 'feathercoin', 'phoenixcoin', 'vertcoin', 'shield']:
                temp_hash = double_sha(header)
                block_hash = binascii.hexlify(hash_util.reverse_bytes(temp_hash)).decode()

            logger.info('Try new block share, worker : %s, share diff : %s' % (_worker_name, share_diff))
            share_result = self.coin_rpc.submit_block(binascii.hexlify(block_hex).decode())

            if share_result is None:
                logger.info('Found Block, result : %s, block hash : %s' % (share_result, block_hash))
                result_hash = Interfaces.block_updater.update_block(repeat=False, block_hash=block_hash)
                if result_hash is not None:
                    block_hash = result_hash
                self.database_ref.insert_accepted_share(username, worker, True, True, _block_template.block_height, share_diff, _block_template.pool_reward, diff, block_hash)
            else:
                logger.error('undefined share_result %s, block hash %s, coinbase tx %s' % (share_result, block_hash, binascii.hexlify(_block_template.coinbase_tx)))
                self.database_ref.insert_accepted_share(username, worker, False, False, _block_template.block_height, share_diff, _block_template.pool_reward, diff)

                if os.getenv("COIN_TYPE") == 'bitcoin':
                    logger.error('Header : %s' % binascii.hexlify(header).decode())
                else:
                    logger.error('Header : %s' % binascii.hexlify(header_soln).decode())
                return {'id': _id, 'result': None, 'error': [20, 'invalid solution']}
        else:
            logger.info('accepted share, worker : %s, share diff : %s' % (_worker_name, '{0:.8f}'.format(share_diff)))
            self.database_ref.insert_accepted_share(username, worker, True, False, _block_template.block_height, share_diff, _block_template.pool_reward, diff)

        return {'id': _id, 'result': True, 'error': None}

    def validate_address(self, _id, _params: list):
        address = _params[0]
        valid_result = self.coin_rpc.validate_address(address)
        return {'id': _id, 'result': valid_result, 'error': None}

    def payout(self, _id, _params: list):
        address = _params[0]
        amount = _params[1]
        username = _params[2]
        payout = _params[3]

        if os.getenv("PAYOUT") == payout:
            wallet = self.database_ref.get_mining_wallet(username)
            coin = self.database_ref.get_coin_info()
            if wallet.balance >= amount + coin.tx_fee:
                save_data = [{'address': address, 'amount': amount, 'username': username}]
                send_data = {address: amount}

                tx_id = self.coin_rpc.send_many(send_data)
                if tx_id is not None:
                    self.database_ref.save_transaction(tx_id, save_data, coin.tx_fee, 'manual')
                    self.database_ref.manual_payout_lock(wallet, amount, coin.tx_fee)

                    logger.info('Manual payout Transaction ID : %s, data %s' % (tx_id, send_data))
                    return {'id': _id, 'result': tx_id, 'error': None}

                return {'id': _id, 'result': None, 'error': [1000, 'Make Transaction Failure']}

    @staticmethod
    def status(_id):
        return {'id': _id, 'result': True, 'error': None}
