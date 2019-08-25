from mining.job_manager import JobManager
from mining.block_updater import BlockUpdater
from mining.database import Database


class Interfaces(object):
    coin_rpc = None
    job_manager = JobManager()
    block_template = None
    block_updater = None
    stratum_handler = None
    database = Database()

    @classmethod
    def set_block_template(cls, block_template):
        cls.block_template = block_template
        cls.block_updater = BlockUpdater(cls.coin_rpc, block_template, cls.database)

    @classmethod
    def set_stratum_handler(cls, stratum_handler):
        cls.stratum_handler = stratum_handler

    @classmethod
    def set_coin_rpc(cls, coin_rpc):
        cls.coin_rpc = coin_rpc
