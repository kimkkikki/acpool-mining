from sqlalchemy.engine import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy import func, case
from sqlalchemy.exc import InvalidRequestError
import os
from mining.models import Block, Shares, Workers, Rewards, Wallets, Coins, Operations, Transactions, ShareStats, Users
from common.logger import get_logger
from datetime import datetime, timedelta
from common.email import send_worker_disconnect_email
from copy import copy

logger = get_logger(__name__)


class Database(object):
    def __init__(self):
        postgres_url = 'postgresql://{}:{}@{}:{}/simple_mining'.format(os.getenv("POSTGRESQL_USER"), os.getenv("POSTGRESQL_PASSWORD"), os.getenv("POSTGRESQL_URL"),
                                                                       os.getenv("POSTGRESQL_PORT"))
        engine = create_engine(postgres_url, client_encoding='utf8')

        session_maker = sessionmaker(bind=engine)
        self.session = session_maker()
        self.coin = None
        self.fee = 2.0  # Default Fee is 2.0%
        self.pool_wallet = None

    def get_user(self, username):
        return self.session.query(Users).filter(Users.username == username).first()

    def insert_block_info(self, height, difficulty, net_hashrate, pool_reward):
        is_exist = self.session.query(Block).\
            filter(Block.coin_name == os.getenv("COIN")).\
            filter(Block.height == height).first()

        pool_reward = pool_reward / 100000000.0
        if is_exist is None:
            block = Block()
            block.coin_name = os.getenv("COIN")
            block.height = height
            block.difficulty = round(difficulty, 3)
            block.net_hashrate = net_hashrate

            if os.getenv("COIN") in ['shield', 'verge']:
                pool_reward = pool_reward * 100

            block.reward = pool_reward

            self.session.add(block)
            logger.debug('New Block Save to database %s' % block)

        else:
            if not is_exist.mined and is_exist.reward != pool_reward:
                is_exist.reward = pool_reward

            is_exist.difficulty = difficulty
            is_exist.net_hashrate = net_hashrate

        self.session.query(Block). \
            filter(Block.coin_name == os.getenv("COIN")). \
            filter(Block.mined.is_(False)). \
            filter(Block.height < height - int(os.getenv("PPLNS_LENGTH"))).delete()
        self.session.commit()

        self.delete_old_infos(height)

    def get_auto_payout_users(self):
        return self.session.query(Wallets). \
            filter(Wallets.coin_name == os.getenv("COIN")). \
            filter(Wallets.payout != 0). \
            filter(Wallets.balance >= Wallets.payout). \
            filter(Wallets.address.isnot(None)). \
            filter(Wallets.type == 'mining').all()

    def orphan_block_rewards_to_zero(self, block_id):
        self.session.query(Rewards). \
            filter(Rewards.block_id == block_id). \
            update({Rewards.reward: 0})
        self.session.query(Block). \
            filter(Block.id == block_id). \
            update({Block.reward: 0})
        self.session.commit()

    def add_confirmed_balance_to_wallet(self, block_id):
        rewards = self.session.query(Rewards). \
            filter(Rewards.block_id == block_id).all()

        for reward in rewards:
            wallet = self.get_mining_wallet(reward.username)
            wallet.balance += reward.reward

        self.session.commit()

    def get_mining_wallet(self, username):
        wallet = self.session.query(Wallets). \
            filter(Wallets.username == username). \
            filter(Wallets.coin_name == os.getenv("COIN")). \
            filter(Wallets.type == 'mining').first()

        if wallet is None:
            wallet = Wallets()
            wallet.username = username
            wallet.coin_name = os.getenv("COIN")
            wallet.type = 'mining'
            self.session.add(wallet)
            self.session.commit()
            self.session.refresh(wallet)

        return wallet

    def found_block_by_pool(self, height, reward, username, _hash):
        # Pool Fee 가져가야함 - Pool 계정만들어서 거기 적립하는 방식? 좋을것 같음.
        # this time mined block

        block = self.session.query(Block).\
            filter(Block.coin_name == os.getenv("COIN")).\
            filter(Block.height == height).first()
        exist = False

        if block is None:
            exist = True
            block = Block()
            block.coin_name = os.getenv("COIN")
            block.height = height

        block.reward = reward / 100000000
        block.mined = True
        block.username = username
        block.hash = _hash
        block.confirmations = 0

        if exist:
            self.session.add(block)
        self.session.commit()

        if exist:
            self.session.refresh(block)  # get block id

        # PPLNS Change
        # Only last 100 Block Share are valid
        share_values = self.session.query(func.sum(Shares.pool_difficulty), Shares.username). \
            filter(Shares.block_height > (height - int(os.getenv("PPLNS_LENGTH")))). \
            filter(Shares.coin_name == os.getenv("COIN")).\
            filter(Shares.pool_result.is_(True)).group_by(Shares.username).all()

        fee_percent = self.fee / 100
        pool_reward = block.reward * fee_percent
        user_reward = block.reward - pool_reward

        total_share_value = 0
        for share_per_user in share_values:
            total_share_value += share_per_user[0]

        # Pool Account reward add
        rewards = Rewards()
        rewards.username = 'admin'
        rewards.block_id = block.id
        rewards.contribution = 0
        rewards.reward = round(pool_reward, 8)
        self.session.add(rewards)

        # Miner Rewards
        for item in share_values:
            rewards = Rewards()
            rewards.username = item[1]
            rewards.block_id = block.id
            rewards.contribution = item[0] / total_share_value
            rewards.reward = round(rewards.contribution * user_reward, 8)
            self.session.add(rewards)

            # TODO: Wallet If not Exist Create
            # self.get_mining_wallet(item[1])

        self.session.commit()

    def insert_accepted_share(self, username, worker, pool_result, share_result, block_height, share_difficulty, reward, target_diff, _hash=None):
        try:
            share = Shares()
            share.coin_name = os.getenv("COIN")
            share.username = username
            share.worker = worker
            share.pool_result = pool_result
            share.share_result = share_result
            share.block_height = block_height
            share.share_difficulty = share_difficulty
            share.pool_difficulty = target_diff

            self.session.add(share)
            self.session.commit()

            if share_result:
                if os.getenv("COIN") in ['shield', 'verge']:
                    reward = reward * 100

                self.found_block_by_pool(block_height, reward, username, _hash)
            logger.debug('New Share Save to database %s' % share)

        except InvalidRequestError:
            self.session.rollback()

    def connected_worker(self, ip, username, worker_name, miner):
        worker = Workers()
        worker.name = worker_name
        worker.username = username
        worker.ip = ip
        worker.miner = miner
        worker.coin_name = os.getenv("COIN")

        self.session.add(worker)
        self.session.commit()
        logger.debug('New Worker Save to database %s' % worker)

        self.get_mining_wallet(username)

    def disconnected_worker(self, username, worker_name, ip):
        disconnect_worker = self.session.query(Workers).\
            filter(Workers.username == username). \
            filter(Workers.name == worker_name).\
            filter(Workers.ip == ip).\
            filter(Workers.disconnected.is_(None)).all()

        if len(disconnect_worker) > 1:
            logger.error('Duplicated worker?')

        for worker in disconnect_worker:
            worker.disconnected = datetime.now()

        self.session.commit()

    def send_disconnected_worker_email(self):
        all_disconnected_workers = self.session.query(Workers, Users).join(Users).\
            filter(Workers.coin_name == os.getenv("COIN")).\
            filter(Workers.disconnected < datetime.utcnow() - timedelta(minutes=10)).all()

        already_email_sends = []
        for worker, user in all_disconnected_workers:
            key = '%s:%s' % (user.username, worker.name)

            if user.email_notification is True and key not in already_email_sends:
                reconnected = self.session.query(Workers).\
                    filter(Workers.coin_name == os.getenv("COIN")).\
                    filter(Workers.username == user.username).\
                    filter(Workers.name == worker.name).\
                    filter(Workers.disconnected.is_(None)).first()

                if reconnected is None:
                    logger.info('Send Email to %s, %s is disconnected' % (user.username, worker.name))
                    send_worker_disconnect_email(user.email, user.username, worker.name, worker.coin_name)
                    already_email_sends.append(key)

        self.session.query(Workers).\
            filter(Workers.coin_name == os.getenv("COIN")).\
            filter(Workers.disconnected < datetime.utcnow() - timedelta(minutes=10))\
            .delete()
        self.session.commit()

    def disconnect_all_worker(self):
        for worker in self.session.query(Workers).\
                filter(Workers.coin_name == os.getenv("COIN")).\
                filter(Workers.disconnected.is_(None)).all():
            worker.disconnected = datetime.now()
        self.session.commit()

    def get_coin_info(self):
        new_coin = self.session.query(Coins).filter(Coins.name == os.getenv("COIN")).first()
        if str(self.coin) != str(new_coin):
            logger.info('Update Coin info %s' % new_coin)
            self.coin = copy(new_coin)
            self.fee = self.coin.fee
            self.pool_wallet = self.get_mining_wallet('admin')

        return self.coin

    def get_need_confirmation_blocks(self, confirmation_count):
        return self.session.query(Block). \
            filter(Block.coin_name == os.getenv("COIN")). \
            filter(Block.mined.is_(True)). \
            filter(Block.confirmations < confirmation_count). \
            filter(Block.confirmations != -1).all()

    def delete_old_infos(self, height):
        self.session.query(Shares). \
            filter(Shares.coin_name == os.getenv("COIN")). \
            filter(Shares.block_height < height - int(os.getenv("PPLNS_LENGTH"))). \
            filter(Shares.share_result.is_(False)). \
            delete()
        self.session.query(Workers).\
            filter(Workers.coin_name == os.getenv("COIN")).\
            filter(Workers.disconnected.isnot(None)).\
            filter(Workers.disconnected < datetime.utcnow() - timedelta(days=1)).\
            delete()
        self.session.commit()

    def get_unfinished_operations(self):
        return self.session.query(Operations).\
            filter(Operations.coin_name == os.getenv("COIN")).\
            filter(Operations.status == 'executing').all()

    def get_unfinished_to_t_address(self):
        return self.session.query(Operations).\
            filter(Operations.coin_name == os.getenv("COIN")).\
            filter(Operations.method == 'to_t_address').\
            filter(Operations.status == 'executing').first()

    def save_or_update_operation(self, op_id, method, status='executing', tx_id=None, message=None):
        operation = self.session.query(Operations).filter(Operations.op_id == op_id).first()
        exist = False
        if operation is None:
            exist = True

        if exist:
            operation = Operations()

        operation.coin_name = os.getenv("COIN")
        operation.op_id = op_id
        if exist:
            operation.method = method
        operation.status = status
        operation.tx_id = tx_id

        if exist:
            self.session.add(operation)
        self.session.commit()

        if not exist and operation.method == 'to_t_address' and status == 'success':
            logger.info('Remove admin account to_t_address_fee')
            self.session.query(Wallets). \
                filter(Wallets.username == 'admin'). \
                filter(Wallets.coin_name == os.getenv("COIN")). \
                filter(Wallets.type == 'mining'). \
                update({Wallets.balance: Wallets.balance - 0.0001})
            self.session.commit()

        if status == 'failed':
            logger.info('Failed Operations : %s' % op_id)
            tx = self.session.query(Transactions).filter(Transactions.op_id == op_id).first()
            tx.confirmations = -1
            tx.block_hash = message

            wallet = self.session.query(Wallets).\
                filter(Wallets.username == tx.username).\
                filter(Wallets.coin_name == os.getenv("COIN")).\
                filter(Wallets.type == 'mining').first()
            wallet.balance = round(wallet.balance + tx.amount + tx.fee, 8)
            wallet.lock_balance = round(wallet.lock_balance - tx.amount - tx.fee, 8)

            self.session.commit()

    def lost_operations_process(self, operations: [Operations]):
        for operation in operations:
            operation.status = 'failed'

            transaction = self.session.query(Transactions).\
                filter(Transactions.op_id == operation.op_id).first()
            if transaction is not None:
                transaction.confirmations = -1

                if transaction.amount is not None and transaction.amount > 0:
                    wallet = self.session.query(Wallets).\
                        filter(Wallets.username == transaction.username).\
                        filter(Wallets.coin_name == os.getenv("COIN")).\
                        filter(Wallets.type == 'mining').first()
                    wallet.lock_balance -= transaction.amount
                    wallet.balance += transaction.amount

        self.session.commit()

    def get_unfinished_shield_coinbase_operation(self):
        return self.session.query(Operations).\
            filter(Operations.coin_name == os.getenv("COIN")).\
            filter(Operations.method == 'z_shieldcoinbase').\
            filter(Operations.status == 'executing').first()

    def save_shield_coinbase_transaction(self, tx_id, params, op_id):
        transaction = Transactions()
        transaction.coin_name = os.getenv("COIN")
        transaction.tx_id = tx_id
        transaction.op_id = op_id
        transaction.username = 'admin'
        transaction.from_address = params['fromaddress']
        transaction.to_address = params['toaddress']
        transaction.fee = abs(params['fee'])
        self.session.add(transaction)
        self.session.commit()

    def lock_balance_wallets(self, wallets: [Wallets]):
        for wallet in wallets:
            wallet.lock_balance += wallet.balance
            wallet.balance = 0

        self.session.commit()

    def manual_payout_lock(self, wallet: Wallets, amount: float, tx_fee: float):
        wallet.lock_balance += amount + tx_fee
        wallet.balance -= amount + tx_fee

        self.session.commit()

    def unlock_balance_wallets(self, wallets: [Wallets]):
        for wallet in wallets:
            wallet.balance += wallet.lock_balance
            wallet.lock_balance = 0

        self.session.commit()

    def remove_lock_balance(self, tx_id, real_fee):
        transactions = self.session.query(Transactions). \
            filter(Transactions.coin_name == os.getenv("COIN")). \
            filter(Transactions.tx_id == tx_id).all()

        user_fees = 0
        for transaction in transactions:
            if transaction.username == 'admin' and transaction.amount is not None:
                continue

            if transaction.amount is None:
                amount = 0
            else:
                amount = transaction.amount

            if transaction.username != 'admin':
                user_fees += abs(transaction.fee)

            wallet = self.session.query(Wallets). \
                filter(Wallets.username == transaction.username). \
                filter(Wallets.coin_name == os.getenv("COIN")). \
                filter(Wallets.type == 'mining'). \
                first()
            wallet.lock_balance = round(wallet.lock_balance - amount - abs(transaction.fee), 8)

        # Auto Payout의 경우 Pool address에서 Fee 만큼 빼기
        total_fee = user_fees - float(abs(real_fee))
        if total_fee != 0:
            logger.info('Total user fee is %s, real fee %s, admin add %s' % (user_fees, real_fee, total_fee))
            self.session.query(Wallets). \
                filter(Wallets.username == 'admin'). \
                filter(Wallets.coin_name == os.getenv("COIN")). \
                filter(Wallets.type == 'mining'). \
                update({Wallets.balance: Wallets.balance + total_fee})
        self.session.commit()

    def save_transaction(self, tx_id, save_data, fee=0, _type='auto', op_id=None):
        for item in save_data:
            transaction = Transactions()
            transaction.coin_name = os.getenv("COIN")
            transaction.tx_id = tx_id
            transaction.op_id = op_id
            transaction.from_address = 'acpool'
            transaction.to_address = item['address']
            transaction.amount = item['amount']
            transaction.username = item['username']
            transaction.fee = abs(fee)
            transaction.type = _type
            self.session.add(transaction)

        self.session.commit()

    def update_transaction(self, tx_id, op_id):
        self.session.query(Transactions). \
            filter(Transactions.op_id == op_id). \
            filter(Transactions.coin_name == os.getenv("COIN")). \
            update({Transactions.tx_id: tx_id})
        self.session.commit()

    def update_transaction_confirmations(self, tx_id, confirmations, block_hash=None):
        self.session.query(Transactions). \
            filter(Transactions.coin_name == os.getenv("COIN")). \
            filter(Transactions.tx_id == tx_id). \
            update({Transactions.confirmations: confirmations,
                    Transactions.block_hash: block_hash})
        self.session.commit()

    def get_unconfirmed_tx_ids(self, need_confirm_count):
        return self.session.query(Transactions.tx_id). \
            filter(Transactions.coin_name == os.getenv("COIN")).\
            filter(Transactions.confirmations >= 0). \
            filter(Transactions.confirmations <= need_confirm_count).\
            filter(Transactions.tx_id.isnot(None)).distinct()

    def update_metric_data(self, start, end):
        metric_raws = self.session. \
            query(func.sum(case([((Shares.pool_result.is_(True)), Shares.pool_difficulty)], else_=None)),
                  func.count(case([((Shares.pool_result.is_(True)), Shares.username)], else_=None)),
                  func.count(case([((Shares.pool_result.is_(False)), Shares.username)], else_=None)),
                  Shares.username,
                  Shares.worker). \
            filter(Shares.timestamp >= start). \
            filter(Shares.timestamp <= end). \
            filter(Shares.coin_name == os.getenv("COIN")). \
            group_by(Shares.worker).group_by(Shares.username).all()

        total_sum = 0
        for metric_raw in metric_raws:
            sum_share_diff = metric_raw[0]
            accepted_share_count = metric_raw[1]
            rejected_share_count = metric_raw[2]
            username = metric_raw[3]
            worker = metric_raw[4]

            share_stat = ShareStats()
            share_stat.username = username
            share_stat.coin_name = os.getenv("COIN")
            share_stat.worker = worker
            share_stat.sum_share_difficulty = sum_share_diff
            share_stat.accepted_share_count = accepted_share_count
            share_stat.rejected_share_count = rejected_share_count
            share_stat.timestamp = end
            self.session.add(share_stat)

            total_sum += sum_share_diff

        # Remove Old metric
        one_day_ago = datetime.utcnow() - timedelta(days=2)
        self.session.query(ShareStats).\
            filter(ShareStats.coin_name == os.getenv("COIN")).\
            filter(ShareStats.timestamp < one_day_ago).\
            delete()

        self.session.query(Coins). \
            filter(Coins.name == os.getenv("COIN")). \
            update({Coins.pool_hash: total_sum})

        self.session.commit()

    def get_or_create_address_user(self, address):
        _user = self.session.query(Users).filter(Users.username == address).first()
        if _user is None:
            _user = Users()
            _user.username = address
            _user.password = os.getenv("COIN")
            _user.email = address
            _user.state = 'addressAccount'
            self.session.add(_user)

        _wallet = self.session.query(Wallets).\
            filter(Wallets.username == address).\
            filter(Wallets.coin_name == os.getenv("COIN")).first()
        if _wallet is None:
            _wallet = Wallets()
            _wallet.username = address
            _wallet.address = address
            _wallet.coin_name = os.getenv("COIN")
            _wallet.type = 'mining'
            _wallet.payout = 0.1
            self.session.add(_wallet)

        self.session.commit()
