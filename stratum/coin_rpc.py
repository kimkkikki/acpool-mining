from common.logger import get_logger
import os
from http import client
from urllib import parse
import base64
import simplejson
import decimal

logger = get_logger(__name__)
USER_AGENT = "SimpleMining/0.1"


def encode_decimal(o):
    if isinstance(o, decimal.Decimal):
        return float(round(o, 8))
    raise TypeError(repr(o) + " is not JSON serializable")


class CoinMethodNotFoundException(Exception):
    code = -32601


class CoinRPC(object):
    def __init__(self):
        logger.debug("Got to Coin RPC")

        user = os.getenv("COIN_DAEMON_USER")
        passwd = os.getenv("COIN_DAEMON_PASSWORD")
        auth_pair = user.encode() + b':' + passwd.encode()
        self.auth_header = b'Basic ' + base64.b64encode(auth_pair)

        url = os.getenv("COIN_DAEMON_HOST")
        port = os.getenv("COIN_DAEMON_PORT")
        url_port = '{}:{}'.format(url, port)
        self.service_url = parse.urlparse(url_port)
        self.port = self.service_url.port

        self.conn = client.HTTPConnection(self.service_url.hostname, self.port, timeout=30)

    def call(self, method, params):
        try:
            post_data = simplejson.dumps({'version': '1.1', 'method': method, 'params': params, 'id': 1}, default=encode_decimal)
            self.conn.request('POST', self.service_url.path, post_data, {
                'Host': self.service_url.hostname,
                'User-Agent': "SimpleMining/0.1",
                'Authorization': self.auth_header,
                'Content-type': 'application/json'
            })
            self.conn.sock.settimeout(30)

            response = self.conn.getresponse()
            response_data = response.read()
            response = simplejson.loads(response_data, parse_float=decimal.Decimal)

            if response['error'] is None:
                return response['result']
            else:
                if response['error']['code'] == -32601:
                    raise CoinMethodNotFoundException(response['error'])
                else:
                    raise Exception(response['error'])

        except (ConnectionResetError, ConnectionRefusedError):
            logger.error('Connection Reset Error')
            self.conn = client.HTTPConnection(self.service_url.hostname, self.port, timeout=30)
            # return self.call(method, params)
        except client.CannotSendRequest:
            logger.error('CannotSendRequest')
            self.conn = client.HTTPConnection(self.service_url.hostname, self.port, timeout=30)

    def get_block_subsidy(self):
        return self.call('getblocksubsidy', [])

    def get_block_template(self, params=None):
        if params is None:
            params = []
        if os.getenv("COIN") == 'phoenixcoin':
            params = [{}]
        return self.call('getblocktemplate', params)

    def get_work_ex(self):
        return self.call('getworkex', [])

    def get_mining_info(self):
        return self.call('getmininginfo', [])

    def submit_block(self, solver):
        if os.getenv("COIN") in ['phoenixcoin']:
            return self.call('getblocktemplate', [{'mode': 'submit', 'data': solver}])
        return self.call('submitblock', [solver])

    def get_block(self, params):
        return self.call('getblock', params)

    def get_block_hash(self, params):
        return self.call('getblockhash', params)

    def list_accounts(self):
        return self.call('listaccounts', [])

    def validate_address(self, address):
        return self.call('validateaddress', [address])

    def send_many(self, send_data):
        try:
            return self.call('sendmany', ['', send_data])
        except Exception as e:
            print(e)
            return None

    def get_transaction(self, tx_id):
        return self.call('gettransaction', [tx_id])

    def get_confirmed_balance(self):
        if os.getenv("COIN_TYPE") == 'zcash':
            total_balance = self.call('z_gettotalbalance', [])
            balance = total_balance['total']
        else:
            balance = self.call('getbalance', [])

        return balance

    def zcash_shield_coinbase(self, to_address):
        if os.getenv("COIN_TYPE") != 'zcash':
            raise Exception('this operations is only supported zcash')

        return self.call('z_shieldcoinbase', ['*', to_address])

    def zcash_operations_status(self, opids):
        if os.getenv("COIN_TYPE") != 'zcash':
            raise Exception('this operations is only supported zcash')

        return self.call('z_getoperationstatus', [opids])

    def zcash_send_many(self, pool_z_address, send_data):
        if os.getenv("COIN_TYPE") != 'zcash':
            raise Exception('this operations is only supported zcash')

        return self.call('z_sendmany', [pool_z_address, send_data])

    def zcash_get_total_balance(self):
        if os.getenv("COIN_TYPE") != 'zcash':
            raise Exception('this operations is only supported zcash')

        return self.call('z_gettotalbalance', [])
