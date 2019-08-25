import struct
import uuid


class JobIdGenerator(object):
    # Generate pseudo-unique job_id. It does not need to be absolutely unique,
    # because pool sends "clean_jobs" flag to clients and they should drop all previous jobs.
    counter = 0

    @classmethod
    def get_new_id(cls):
        cls.counter += 1
        if cls.counter % 0xffff == 0:
            cls.counter = 1
        return "%x" % cls.counter


class SessionIdGenerator(object):
    @staticmethod
    def get_session_id():
        return str(uuid.uuid4()).replace('-', '')


class NonceGenerator(object):
    def __init__(self, instance_id):
        self.counter = instance_id << 27
        self.size = struct.calcsize('>L')

    def get_size(self):
        # Return expected size of generated extranonce in bytes
        return self.size

    def get_new_nonce(self):
        self.counter += 1
        return struct.pack('>L', self.counter)
