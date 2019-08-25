import asyncio
import simplejson
from mining.interfaces import Interfaces
from common.generators import SessionIdGenerator
from common.logger import get_logger
from common.cache import mc

logger = get_logger(__name__)


class StratumProtocol(asyncio.Protocol):
    def __init__(self):
        self.transport = None
        self.handler = Interfaces.stratum_handler
        self.request_counter = None
        self.session_id_generator = SessionIdGenerator()
        self.session_id = None
        self.job_manager = Interfaces.job_manager
        self._buffer = b''
        self.miner_program = None
        self.worker_name = None
        self.username = None
        self.host = None
        self.ip = None

    def get_session(self):
        return self.session_id

    def check_banned_ip(self):
        fail_key = 'ban::%s' % self.ip
        fail_count = mc.get(fail_key)
        if fail_count is not None and fail_count > 50:
            return True

        return False

    def increase_failure(self):
        fail_key = 'ban::%s' % self.ip
        fail_count = mc.get(fail_key)
        if fail_count is None:
            mc.set(fail_key, 1, time=60)
        else:
            mc.set(fail_key, fail_count + 1, time=60)

    def connection_made(self, transport):
        connector_address = transport.get_extra_info('peername')
        logger.debug("Connected %s:%s" % (connector_address[0], connector_address[1]))
        self.transport = transport
        self.host = '%s:%s' % (connector_address[0], connector_address[1])
        self.ip = connector_address[0]
        self.session_id = self.session_id_generator.get_session_id()
        self.job_manager.connections.add(self)

    def connection_lost(self, exc):
        logger.debug("Disconnected %s" % self.host)
        if '127.0.0.1' not in self.host:
            logger.info('Disconnected %s, %s ' % (self.host, exc))
        self.handler.disconnect(self)
        self.job_manager.connections.remove(self)

    def resume_writing(self):
        logger.info('resume_writing!!')

    def data_received(self, data):
        if self.check_banned_ip():
            self.send_message({'id': 0, 'result': None, 'error': ['Your IP Is Temporary banned. DDoS attack is suspected.']})
            logger.info('Seems like DDoS Attack, %s' % self.ip)
            self.transport.close()
            return

        if b'\n' in data:
            _data = data.split(b'\n')

            temp = None
            if _data[-1] != b'':
                temp = _data[-1]

            _data.pop(-1)

            for _line in _data:
                if self._buffer != b'':
                    _line = self._buffer + _line
                    self._buffer = b''

                try:
                    _json = simplejson.loads(_line)
                    self.line_received(_json)

                except simplejson.JSONDecodeError:
                    logger.debug('json decode fail %s ' % _line)
                    self.increase_failure()

            if temp is not None:
                self._buffer += temp
        else:
            self._buffer += data

    def line_received(self, line):
        logger.debug('lineReceived : %s', line)

        result = self.handler.handle_event(self, line)
        self.send_message(result)

        if line.get('method') == 'mining.authorize':
            self.handler.notify(self, True)

        if result is None or result['error'] is not None:
            self.increase_failure()

    def send_message(self, result):
        logger.debug('send message : %s', result)
        json_str = simplejson.dumps(result)

        if self.transport is not None:
            self.transport.write(('%s\n' % json_str).encode())
