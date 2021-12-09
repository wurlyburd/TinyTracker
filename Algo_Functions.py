from algosdk.v2client.indexer import IndexerClient
from algosdk.v2client.algod import AlgodClient
from tinyman.v1.client import TinymanMainnetClient
from tinyman.v1.pools import get_pool_info_from_account_info
import datetime
import statistics

class AlgoTools:
    def __init__(self, address = None):
        ### Setup Stuff ###
        self.indexer_address = 'https://algoexplorerapi.io/idx2'
        self.indexer_token = ''
        self.algod_address = 'https://algoexplorerapi.io'
        self.algod_token = ''
        self.address = address

        # Set up API instances
        self.indexer_client = IndexerClient(self.indexer_token, self.indexer_address, headers={'User-Agent': 'algosdk'})
        self.algod_client = AlgodClient(self.algod_token, self.algod_address, headers={'User-Agent': 'algosdk'})
        self.tiny = TinymanMainnetClient(algod_client=self.algod_client, user_address=self.address)
        ### End Setup ###

    ### Start Functions ###
    def GetPools(self, address):
        # Creates a dict of all tinyman pools associated with address.
        # Contents of each pool will have:
        #    'pair_name'
        #    'pool_id'
        #    'asset1'
        #    'asset2'
        
        all_pools = {}
        tp = 0
        algod = self.algod_client.account_info(address)
        for asset in algod['assets']:
            # Look for tinyman assets and pull pools.
            try:
                asset_info = self.algod_client.asset_info(asset['asset-id'])
            except:
                continue
            asset_name = asset_info['params']['name']
            if 'Tinyman Pool' in asset_name:
                tinypool = {}

                pool_info = self.algod_client.account_info(asset_info['params']['creator'])
                pool = get_pool_info_from_account_info(pool_info)

                asset1 = self.tiny.fetch_asset(pool['asset1_id'])
                asset2 = self.tiny.fetch_asset(pool['asset2_id'])

                tinypool['pair_name'] = asset_name
                tinypool['pool_id'] = pool['liquidity_asset_id']
                tinypool['asset1'] = asset1
                tinypool['asset2'] = asset2

                all_pools[tp] = tinypool
                tp = tp+1
                del tinypool
            
        return all_pools
#####
    def ConvertDate(self, date):
        if isinstance(date, str):
            newdate = datetime.datetime.strptime(date, '%Y-%m-%d %H:%M:%S')
        elif isinstance(date, datetime.datetime):
            newdate = date
        newstrdate = str(newdate.day) + '-' + str(newdate.month) + '-' + str(newdate.year)
        return newstrdate
#####
    def CalculateAPY(self, value_start, value_now, day1, today = datetime.datetime.now()):
        # Not quite ready for prime time
        if isinstance(day1, str):
            day1_dt = datetime.datetime.strptime(day1, '%d-%m-%Y')
        deltadate = today - day1_dt
        APY = ((value_now / value_start) - 1) * (deltadate.days) / 365
        return APY
#####
    def GetPriceFromPool(self, ASSET, block_id = 0, num_blocks = 133): # 133 ~ +/-10 minutes from transaction
        ALGO = self.tiny.fetch_asset(0)
        pool = self.tiny.fetch_pool(ALGO, ASSET)
        if block_id == 0:
            # Current price
            quote = pool.fetch_fixed_input_swap_quote(ALGO(1_000_000), slippage=0.01)
            asset_price = 1/(quote.amount_out.amount * 10**(-ASSET.decimals))
        else:
            tx_past = self.indexer_client.search_transactions_by_address(pool.address, 
                                                                         min_round = block_id-num_blocks, 
                                                                         max_round = block_id+num_blocks)
            groupID_last = None
            algo_per_asset = []
            asset_amt = 0
            algo_amt = 0

            for tx in tx_past['transactions']:
                if 'group' not in tx:
                    # Skip if tx is not part of a group
                    continue
                elif asset_amt != 0 and algo_amt != 0:
                    # After getting an asset value and algo value, calculate the price
                    algo_per_asset.append(algo_amt / asset_amt)
                    continue
                elif tx['group'] != groupID_last:
                    # Start a new group transaction to calculate price
                    groupID_last = tx['group']
                    asset_amt = 0
                    algo_amt = 0
                else:
                    if tx['tx-type'] == 'axfer':
                        if tx['asset-transfer-transaction']['asset-id'] == ASSET.id:
                            asset_amt = tx['asset-transfer-transaction']['amount'] * 10**(-ASSET.decimals)
                    elif tx['tx-type'] == 'pay':
                        # Check if the value is >A0.01 as this would most likely be a fee
                        if tx['payment-transaction']['amount'] >= 1e4:
                            algo_amt = tx['payment-transaction']['amount'] * 10**(-ALGO.decimals)
                
            if len(algo_per_asset) < 10: # Use minimum 10 txns to get an average
                if num_blocks >= 3192:
                    # Stops trying after timespan = 8 hours (+/-4 hours)
                    print('Could not find enough transactions to estimate price.')
                    asset_price = -1
                else:
                    # Keep adding +/-10 minutes until we get enough data
                    print('Time band: +/-' + str(num_blocks/13.3 + 10) + ' minutes')
                    asset_price = self.GetPriceFromPool(ASSET, block_id, num_blocks+133)
            else:
                # Use the median to calculate the price to ensure lopsided trades are not included
                asset_price = statistics.median(algo_per_asset)
        
        return asset_price
#####
    def ALGOtoUSD(self, price_in_algo, usdc_price_algo, usdt_price_algo):
        usd_price_algo = (usdc_price_algo + usdt_price_algo) / 2
        # Average of usdc and usdt in case one of them is a bit off from the dollar
        asset_price_usd = price_in_algo / usd_price_algo
        return asset_price_usd

### End Functions ###