from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy import Column, Integer, String, Float, Boolean, ForeignKey, DateTime, func
import datetime

Base = declarative_base()


class Coins(Base):
    __tablename__ = 'coins'

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False, unique=True, index=True)
    algorithm = Column(String, nullable=False)
    port = Column(Integer, nullable=False)
    pool_hash = Column(Float, default=0)
    usd_price = Column(Float, default=0)
    btc_price = Column(Float, default=0)
    confirmation_count = Column(Integer)
    pool_address = Column(String)
    shield_address = Column(String)
    fee = Column(Float, default=2.0)
    tx_fee = Column(Float, default=0.0001)
    open = Column(Boolean, default=True, index=True)

    def __str__(self):
        return '<Coins id: %s, name: %s, algorithm: %s, port: %s, fee: %s, confirmation_count: %s, pool_address: %s, tx_fee: %s>' % \
               (self.id, self.name, self.algorithm, self.port, self.fee, self.confirmation_count, self.pool_address, self.tx_fee)

    def __eq__(self, other):
        return str(self) == str(other)


class Shares(Base):
    __tablename__ = 'shares'

    id = Column(Integer, primary_key=True, autoincrement=True)
    coin_name = Column(String, ForeignKey('coins.name'), index=True)
    coin = relationship("Coins")
    username = Column(String, ForeignKey('users.username'), index=True)
    user = relationship("Users")
    worker = Column(String)
    pool_result = Column(Boolean, index=True)
    share_result = Column(Boolean)
    block_height = Column(Integer, index=True)
    share_difficulty = Column(Float)
    pool_difficulty = Column(Float)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow, index=True)

    def __str__(self):
        return '<Share id: %s, coin_name: %s, username: %s, worker: %s, pool_difficulty: %s' \
               ', pool_result: %r,' \
               ' share_result: %r, height: %s, share_diff: %s, timestamp: %s>' % \
               (self.id, self.coin_name, self.username, self.worker, self.pool_difficulty,
                self.pool_result, self.share_result, self.block_height, self.share_difficulty, self.timestamp)


class ShareStats(Base):
    __tablename__ = 'share_stat'

    id = Column(Integer, primary_key=True, autoincrement=True)
    coin_name = Column(String, ForeignKey('coins.name'), index=True)
    coin = relationship("Coins")
    username = Column(String, ForeignKey('users.username'), index=True)
    user = relationship("Users")
    worker = Column(String)
    sum_share_difficulty = Column(Float)
    accepted_share_count = Column(Integer)
    rejected_share_count = Column(Integer)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow, index=True)


class Block(Base):
    __tablename__ = 'block'

    id = Column(Integer, primary_key=True, autoincrement=True)
    coin_name = Column(String, ForeignKey('coins.name'), index=True)
    coin = relationship("Coins")
    height = Column(Integer, index=True)
    difficulty = Column(Float)
    net_hashrate = Column(Float)
    reward = Column(Float)
    mined = Column(Boolean, default=False)
    hash = Column(String)
    confirmations = Column(Integer, index=True)
    username = Column(String, ForeignKey('users.username'))
    user = relationship("Users")
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)

    def __str__(self):
        return '<Block id: %s, coin_name: %s, height: %s, difficulty: %s, net_hashrate: %s, reward: %s, mined: %s, timestamp: %s>' % \
               (self.id, self.coin_name, self.height, self.difficulty, self.net_hashrate, self.reward, self.mined, self.timestamp)


class Wallets(Base):
    __tablename__ = 'wallets'

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String, ForeignKey('users.username'), index=True)
    user = relationship("Users", back_populates="wallets")
    coin_name = Column(String, ForeignKey('coins.name'), index=True)
    coin = relationship("Coins")
    address = Column(String, index=True)
    balance = Column(Float, default=0)
    lock_balance = Column(Float, default=0, comment='Before transaction completed')
    label = Column(String)
    type = Column(String, default='acpool')
    payout = Column(Float, default=0, comment='0 means no auto payout')
    timestamp = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)

    def __str__(self):
        return '<Wallets id: %s, username: %s, coin_name: %s, address: %s, balance: %s, timestamp: %s>' % \
               (self.id, self.username, self.coin_name, self.address, self.balance, self.timestamp)


class Rewards(Base):
    __tablename__ = 'rewards'

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String, ForeignKey('users.username'), index=True)
    user = relationship("Users")
    block_id = Column(Integer, ForeignKey('block.id'))
    block = relationship("Block", backref='rewards')
    contribution = Column(Float)
    reward = Column(Float)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow, nullable=False, index=True)

    def __str__(self):
        return '<Rewards id: %s, username: %s, block_id: %s, contribution: %s, reward: %s, timestamp: %s>' % \
               (self.id, self.username, self.block_id, self.contribution, self.reward, self.timestamp)


class Users(Base):
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String, nullable=False, unique=True, index=True)
    wallets = relationship("Wallets", back_populates="user")
    password = Column(String, nullable=False)
    email = Column(String, nullable=False, unique=True, index=True)
    state = Column(String, default='NeedValidateEmail', nullable=False)
    otp_key = Column(String, nullable=True)
    otp_state = Column(Boolean, default=False)
    email_notification = Column(Boolean, default=False)
    created = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    updated = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)

    def __str__(self):
        return '<User id: %s, username: %s, password: %s, email: %s, state: %s, otp_key: %s, opt_state: %s, created: %s, updated: %s>' % \
               (self.id, self.username, self.password, self.email, self.state, self.otp_key, self.otp_state, self.created, self.updated)


class Workers(Base):
    __tablename__ = 'workers'

    id = Column(Integer, primary_key=True, autoincrement=True)
    ip = Column(String, nullable=False)
    username = Column(String, ForeignKey('users.username'))
    user = relationship("Users")
    coin_name = Column(String, ForeignKey('coins.name'))
    coin = relationship("Coins")
    name = Column(String, default='default')
    miner = Column(String)
    connected = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    disconnected = Column(DateTime, nullable=True)

    def __str__(self):
        return '<Workers id: %s ip: %s, username: %s, coin_name: %s, name: %s, miner: %s, connected: %s, disconnected: %s>' % \
               (self.id, self.ip, self.username, self.coin_name, self.name, self.miner, self.connected, self.disconnected)


class Operations(Base):
    __tablename__ = 'operations'

    id = Column(Integer, primary_key=True, autoincrement=True)
    op_id = Column(String, nullable=False, index=True)
    coin_name = Column(String, ForeignKey('coins.name'), index=True)
    coin = relationship("Coins")
    tx_id = Column(String)
    status = Column(String, default='executing', index=True)
    method = Column(String)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)

    def __str__(self):
        return self.op_id


class Transactions(Base):
    __tablename__ = 'transactions'

    id = Column(Integer, primary_key=True, autoincrement=True)
    op_id = Column(String, ForeignKey('operations.op_id'), index=True)
    operation = relationship("Operations")
    tx_id = Column(String, index=True)
    coin_name = Column(String, ForeignKey('coins.name'), index=True)
    coin = relationship("Coins")
    username = Column(String, ForeignKey('users.username'), index=True)
    user = relationship("Users")
    block_hash = Column(String)
    type = Column(String, default='auto')
    from_address = Column(String, index=True, nullable=False)
    to_address = Column(String, index=True, nullable=False)
    amount = Column(Float)
    fee = Column(Float)
    confirmations = Column(Integer, default=0, index=True)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)

    def __str__(self):
        return self.tx_id
