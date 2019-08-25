from dotenv import load_dotenv
load_dotenv()

import asyncio
from mining.interfaces import Interfaces
from stratum.protocol import StratumProtocol
from stratum.coin_rpc import CoinRPC
from mining.block_template import BlockTemplate
from mining.metric_generator import MetricGenerator
from stratum.handler import ACPoolHandler
import signal
import sys

if len(sys.argv) <= 1:
    raise Exception('Coin name is not set.')

if len(sys.argv) == 2:
    net_type = 'testnet'
else:
    net_type = sys.argv[2]

coin_name = sys.argv[1]


def kill_handler(_signal, _frame):
    db.disconnect_all_worker()
    sys.exit(0)


signal.signal(signal.SIGTERM, kill_handler)
signal.signal(signal.SIGINT, kill_handler)

db = Interfaces.database
coin = db.get_coin_info()
if coin is None:
    raise Exception('Coin {} is not found. You must first set up the database.'.format(coin.name))
elif coin.pool_address is None:
    raise Exception('Coin Pool Address is null.')

Interfaces.set_coin_rpc(CoinRPC())
Interfaces.set_block_template(BlockTemplate(coin.pool_address))
Interfaces.set_stratum_handler(ACPoolHandler())

MetricGenerator(db)

loop = asyncio.get_event_loop()
coro = loop.create_server(StratumProtocol, host='0.0.0.0', port=coin.port)
server = loop.run_until_complete(coro)

try:
    loop.run_forever()
except KeyboardInterrupt:
    pass

server.close()
loop.run_until_complete(server.wait_closed())
loop.close()
