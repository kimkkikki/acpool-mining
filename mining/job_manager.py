import struct
import binascii
import os
from collections import OrderedDict
from copy import copy


class JobManager(object):
    def __init__(self):
        self.nonces = {}
        self.jobs = {}
        self.block_templates = OrderedDict()
        self.job_counter = 0
        self.size = struct.calcsize('>L')
        self.connections = set()
        self.submits = set()

    def get_nonce_size(self):
        # Return expected size of generated extranonce in bytes
        return self.size

    def get_nonce_from_session_id(self, session_id):
        return self.nonces[session_id]

    def get_new_nonce(self, session_id):
        new_nonce = struct.unpack("<L", os.urandom(4))[0]
        nonce = struct.pack('>L', new_nonce)
        nonce = binascii.hexlify(nonce)
        self.nonces[session_id] = nonce

        return nonce

    def get_new_job_id(self, session_id, block_template):
        self.job_counter += 1
        if self.job_counter % 0xffff == 0:
            self.job_counter = 1
        job_id = "%x" % self.job_counter
        self.jobs[session_id] = job_id
        self.block_templates[job_id] = copy(block_template)

        if len(self.block_templates) > len(self.connections) * 3:
            self.block_templates.popitem(last=False)

        return job_id

    def get_block_template(self, job_id):
        if job_id in self.block_templates:
            return self.block_templates[job_id]
        else:
            return None

    def register_submit(self, nonce_1, nonce_2, nonce, time) -> bool:
        submit = (nonce_1, nonce_2, nonce, time)
        if submit in self.submits:
            return False
        else:
            self.submits.add(submit)
            return True

    def clear_submits(self):
        self.submits.clear()
