from mining.database import Database
from mining.models import Block, Rewards, Transactions, Wallets, func
import asyncio
from datetime import datetime, timedelta
from common.logger import get_logger
import os

logger = get_logger(__name__)


class MetricGenerator(object):
    def __init__(self, database: Database):
        self.database_ref = database
        now = datetime.now()
        self.when = now.replace(minute=now.minute - (now.minute % 10), second=0, microsecond=0)
        asyncio.get_event_loop().call_later(self.ten_minute_later(), self.generate_metric)
        self.synchronize_database()
        # self.adjustment_balances()

    def ten_minute_later(self):
        when = self.when + timedelta(minutes=10)
        self.when = when.replace(second=0, microsecond=0)
        later = self.when - datetime.now()
        return later.total_seconds()

    def generate_metric(self):
        asyncio.get_event_loop().call_later(self.ten_minute_later(), self.generate_metric)

        end = datetime.utcnow().replace(second=0, microsecond=0)
        start = end - timedelta(minutes=10)
        logger.info('Generate metric, %s to %s' % (start, end))
        self.database_ref.update_metric_data(start, end)
        self.database_ref.send_disconnected_worker_email()

    def synchronize_database(self):
        uncommon_orphans = self.database_ref.session.query(Block). \
            filter(Block.coin_name == os.getenv("COIN")).\
            filter(Block.confirmations == -1).\
            filter(Block.reward != 0).all()

        for uncommon_orphan_block in uncommon_orphans:
            self.database_ref.session.query(Rewards). \
                filter(Rewards.block_id == uncommon_orphan_block.id). \
                update({Rewards.reward: 0})
            uncommon_orphan_block.reward = 0

    def adjustment_balances(self):
        from mining.interfaces import Interfaces
        import settings

        coin_rpc = Interfaces.coin_rpc
        # TODO: balance synchronize 해야할 것 같음
        coin = self.database_ref.get_coin_info()
        rewards = self.database_ref.session. \
            query(func.sum(Rewards.reward), Rewards.username).join(Block). \
            filter(Block.confirmations > coin.confirmation_count). \
            filter(Block.coin_name == settings.COIN). \
            group_by(Rewards.username).all()
        transactions = self.database_ref.session. \
            query(func.sum(Transactions.amount), func.sum(Transactions.fee), Transactions.username). \
            filter(Transactions.coin_name == settings.COIN). \
            group_by(Transactions.username).all()
        wallets = self.database_ref.session.query(Wallets). \
            filter(Wallets.coin_name == settings.COIN). \
            filter(Wallets.type == 'mining').all()

        confirmed_balance = coin_rpc.get_confirmed_balance()

        merged_tuple = []
        total_rewards = 0
        total_tx_out = 0

        for wallet in wallets:
            reward = 0
            for item in rewards:
                if item[1] == wallet.username:
                    reward = item[0]
                    rewards.remove(item)

            transaction_amount = 0
            transaction_fee = 0
            for item in transactions:
                if item[2] == wallet.username:
                    transaction_amount = item[0] if item[0] is not None else 0
                    transaction_fee = item[1] if item[1] is not None else 0
                    transactions.remove(item)

            total_rewards += reward
            total_tx_out += transaction_amount
            total_tx_out -= transaction_fee

            merged_tuple.append((wallet.username, wallet.balance, reward, transaction_amount, transaction_fee))

        unpaid_balance = round(float(confirmed_balance) - (total_rewards - total_tx_out), 8)

        # Balance adjustment
        admin_data = None
        for raw in merged_tuple:
            if raw[0] != 'admin' and round(raw[1], 8) != round(raw[2] - raw[3], 8):
                logger.info('Balance adjustment user <%s>, %s to %s' % (raw[0], raw[1], raw[2] - raw[3]))
                self.database_ref.session.query(Wallets). \
                    filter(Wallets.username == raw[0]). \
                    filter(Wallets.coin_name == settings.COIN). \
                    filter(Wallets.type == 'mining'). \
                    update({Wallets.balance: raw[2] - raw[3]})

            elif raw[0] == 'admin':
                admin_data = raw

        if unpaid_balance != 0 and admin_data is not None:
            if unpaid_balance != admin_data[1] - (admin_data[2] - admin_data[3]):
                logger.info('Unpaid balance set <admin>, %s' % unpaid_balance)
                self.database_ref.session.query(Wallets). \
                    filter(Wallets.username == 'admin'). \
                    filter(Wallets.coin_name == settings.COIN). \
                    filter(Wallets.type == 'mining'). \
                    update({Wallets.balance: unpaid_balance})

        self.database_ref.session.commit()
