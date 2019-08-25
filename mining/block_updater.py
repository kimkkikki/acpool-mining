from stratum.coin_rpc import CoinRPC, CoinMethodNotFoundException
import os
from common.logger import get_logger
from mining.database import Database
import simplejson
import asyncio

logger = get_logger(__name__)


class BlockUpdater(object):
    def __init__(self, coin_rpc: CoinRPC, block_template, database: Database):
        self.coin_rpc = coin_rpc
        self.block_template = block_template
        self.prev_hash = ''
        self.merkle_interval = float(os.getenv("MERKLE_UPDATE_INTERVAL"))
        self.database_ref = database

        coin = self.database_ref.get_coin_info()
        self.confirmation_count = coin.confirmation_count
        self.pool_address = coin.pool_address

        if os.getenv("COIN_TYPE") == 'zcash':
            self.shield_address = coin.shield_address

        self.update_coin_reward()
        self.update_block()

    def update_coin_reward(self):
        try:
            subsidy = self.coin_rpc.get_block_subsidy()
            if 'founders' in subsidy:
                if os.getenv("COIN") == 'bitcoin-interest' or os.getenv("COIN") == 'bitcoin-gold':
                    block_reward = subsidy['miner'] + subsidy['founders']
                else:
                    block_reward = (subsidy['miner'] + subsidy['founders']) * 100000000
            else:
                block_reward = subsidy['miner'] * 100000000

            self.block_template.subsidy = True
            self.block_template.block_reward = block_reward
        except CoinMethodNotFoundException:
            pass
        except simplejson.JSONDecodeError:
            pass
        except Exception:
            pass

    def check_unconfirmed_transactions(self):
        # TODO: transaction confirmation count 정해야함
        confirmed_count = 10
        tx_ids = self.database_ref.get_unconfirmed_tx_ids(confirmed_count)
        for tx_id in tx_ids:
            result = self.coin_rpc.get_transaction(tx_id[0])
            confirmations = result['confirmations']

            block_hash = None
            if 'blockhash' in result:
                block_hash = result['blockhash']

            self.database_ref.update_transaction_confirmations(result['txid'], confirmations, block_hash)

            # Remove lock balance
            if confirmations > confirmed_count:
                if 'fee' in result:
                    fee = result['fee']
                else:
                    fee = 0

                self.database_ref.remove_lock_balance(result['txid'], real_fee=fee)

    def send_auto_payout(self):
        # DB에서 wallet balance가 auto payout을 설정한 양 이상이 되는 애들에게 전송
        wallets = self.database_ref.get_auto_payout_users()
        if len(wallets) > 0:
            logger.info('New auto payout transaction %s' % len(wallets))

            # TODO: Transaction fee 부과해야하는데..
            # coin = self.database_ref.get_coin_info()
            # tx_fee_per_user = coin.tx_fee / len(wallets)

            save_data = []
            send_data = {}
            for wallet in wallets:
                # balance = wallet.balance - tx_fee_per_user
                balance = wallet.balance
                send_data[wallet.address] = balance
                save_data.append({'address': wallet.address, 'amount': balance, 'username': wallet.username})

            tx_id = self.coin_rpc.send_many(send_data)
            if tx_id is not None:
                self.database_ref.save_transaction(tx_id=tx_id, save_data=save_data)
                self.database_ref.lock_balance_wallets(wallets)

                logger.info('Auto payout Transaction ID : %s, data %s' % (tx_id, send_data))

    def update_confirmations(self):
        need_confirm_blocks = self.database_ref.get_need_confirmation_blocks(self.confirmation_count + 1)

        for block in need_confirm_blocks:
            try:
                block_data = self.coin_rpc.get_block([block.hash])
                block.confirmations = block_data['confirmations']

                # Orphan Block
                if block.confirmations == -1:
                    self.database_ref.orphan_block_rewards_to_zero(block.id)

                elif block_data['confirmations'] >= self.confirmation_count + 1:
                    self.database_ref.add_confirmed_balance_to_wallet(block.id)

            except Exception as e:
                # Sometimes Header hash != block hash (ex: monacoin testnet)
                if block.confirmations == 0:
                    block_hash = self.coin_rpc.get_block_hash([block.height])
                    block_data = self.coin_rpc.get_block([block_hash])
                    block.confirmations = block_data['confirmations']
                    block.hash = block_hash
                else:
                    logger.error('NotFound Block %s, message : %s' % (block.hash, e))

        if len(need_confirm_blocks) > 0:
            self.database_ref.session.commit()

        if os.getenv("PAYOUT_TYPE") == 'zcash':
            try:
                unfinished_shield_coinbase = self.database_ref.get_unfinished_shield_coinbase_operation()
                if unfinished_shield_coinbase is None:
                    shield_coinbase = self.coin_rpc.zcash_shield_coinbase(self.shield_address)
                    self.database_ref.save_or_update_operation(shield_coinbase['opid'], 'z_shieldcoinbase')
                    logger.info('New Shield Coinbase, Operation : %s' % shield_coinbase['opid'])
            except Exception:
                pass

            unfinished_operations = self.database_ref.get_unfinished_operations()
            if len(unfinished_operations) != 0:
                unfinished_operations_ids = [item.op_id for item in unfinished_operations]
                operations_status = self.coin_rpc.zcash_operations_status(unfinished_operations_ids)
                for operation in operations_status:
                    unfinished_operations_ids.remove(operation['id'])
                    if operation['status'] == 'success':
                        transaction_id = operation['result']['txid']
                        operation_method = operation['method']
                        self.database_ref.save_or_update_operation(operation['id'], operation_method, operation['status'], transaction_id)
                        if operation_method == 'z_shieldcoinbase':
                            self.database_ref.save_shield_coinbase_transaction(transaction_id, operation['params'], operation['id'])
                            logger.info('New Shield Coinbase Transaction : %s' % transaction_id)
                        else:
                            logger.info('New Operation %s, Transaction : %s' % (operation['id'], transaction_id))
                            self.database_ref.update_transaction(transaction_id, operation['id'])

                    elif operation['status'] == 'failed':
                        operation_method = operation['method']
                        error_message = None
                        if 'error' in operation:
                            error_message = operation['error']['message']
                        self.database_ref.save_or_update_operation(operation['id'], operation_method, operation['status'], None, error_message)

                if len(unfinished_operations_ids) > 0:
                    # Lost operations..
                    operations = []
                    for op_id in unfinished_operations_ids:
                        for item in unfinished_operations:
                            if item.op_id == op_id:
                                operations.append(item)
                                break

                    logger.info('Lost Operations : %s' % unfinished_operations_ids)
                    self.database_ref.lost_operations_process(operations)

    def shield_to_transparent_address(self):
        unfinished_to_t_address = self.database_ref.get_unfinished_to_t_address()
        if unfinished_to_t_address is None:
            total_balance = self.coin_rpc.zcash_get_total_balance()
            private_balance = round(float(total_balance['private']) - 0.0001, 8)
            if private_balance > 0:
                if os.getenv("COIN") == 'buck' and private_balance > 50000:
                    private_balance = 50000
                pool_address = self.pool_address

                send_data = [{'address': pool_address, 'amount': private_balance}]
                save_data = [{'address': pool_address, 'amount': private_balance, 'username': 'admin'}]
                logger.info('Shield to T address, Try data %s' % send_data)

                operation = self.coin_rpc.zcash_send_many(self.shield_address, send_data)
                self.database_ref.save_or_update_operation(operation, 'to_t_address')
                self.database_ref.save_transaction(tx_id=None, save_data=save_data, op_id=operation)
                logger.info('Shield to T address operation : %s, data %s' % (operation, send_data))

    def update_block(self, repeat=True, block_hash=None):
        if repeat:
            asyncio.get_event_loop().call_later(float(os.getenv("BLOCK_UPDATE_INTERVAL")), self.update_block)

        logger.debug('Check new block')
        data = self.coin_rpc.get_block_template([])

        if data is None:
            logger.error('update_block failed, response is None')
            return None

        if self.prev_hash != data['previousblockhash']:
            self.prev_hash = data['previousblockhash']
            logger.info('Found New Block, previous hash is %s' % data['previousblockhash'])
            self.block_template.block_update(data)
            self.block_template.merkle_update(data, notify=True)
            self.merkle_interval = float(os.getenv("MERKLE_UPDATE_INTERVAL"))

            mining_info = self.coin_rpc.get_mining_info()
            if mining_info is not None:
                if 'powdifficulty' in mining_info:
                    difficulty = mining_info['powdifficulty']
                else:
                    difficulty = mining_info['difficulty']

                if 'networkhashps' in mining_info:
                    net_hashrate = mining_info['networkhashps']
                elif 'hashespersec' in mining_info:
                    net_hashrate = mining_info['hashespersec']
                else:
                    raise Exception('net hashrate not found')

                self.database_ref.insert_block_info(mining_info['blocks'], difficulty, net_hashrate, self.block_template.pool_reward)

            self.update_confirmations()
            self.send_auto_payout()
            self.check_unconfirmed_transactions()

            if os.getenv("PAYOUT_TYPE") == 'zcash':
                self.shield_to_transparent_address()

            # Refresh Coin data, Fee, Wallet address.
            self.database_ref.get_coin_info()

            if not repeat and block_hash != data['previousblockhash']:
                return data['previousblockhash']

        else:
            if self.merkle_interval <= 0:
                logger.debug('Check new merkle')
                self.block_template.merkle_update(data, notify=False)
                self.merkle_interval = float(os.getenv("MERKLE_UPDATE_INTERVAL"))
            else:
                self.merkle_interval -= float(os.getenv("BLOCK_UPDATE_INTERVAL"))

        return None
