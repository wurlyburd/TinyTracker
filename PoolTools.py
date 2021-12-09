from os import system
from algosdk import encoding
from algosdk.v2client.algod import AlgodClient
from algosdk.v2client.indexer import IndexerClient
from tinyman.v1.client import TinymanMainnetClient
from Algo_Functions import AlgoTools
import datetime
import csv
import sys

filename = 'Tinypools.csv' # Name of csv file to write (appends data)
writetofile = True # Set to false to not print to csv

indexer_address = 'https://algoexplorerapi.io/idx2'
indexer_token = ''
algod_address = 'https://algoexplorerapi.io'
algod_token = ''

address = input('Enter address: ')
if not encoding.is_valid_address(address):
    sys.exit('Address is not valid')
#address = '' # Add address here for automation

# Set up API instances
algod_client = AlgodClient(algod_token, algod_address, headers={'User-Agent': 'algosdk'})
indexer_client = IndexerClient(indexer_token, indexer_address, headers={'User-Agent': 'algosdk'})
tiny = TinymanMainnetClient(algod_client=algod_client, user_address=address)
algotools = AlgoTools(address)
### End Setup ###

# So that we don't keep querying the indexer, only pull the transactions once and put them in a dict
# to be used throughout the code
transact_dict_all = indexer_client.search_transactions_by_address(address)

# Get all pools associated with address
tinypools = algotools.GetPools(address)

# Assets we are guaranteed to use for pricing so establish them now
ALGO = tiny.fetch_asset(0)
USDC = tiny.fetch_asset(31566704)
USDT = tiny.fetch_asset(312769)

def ReduceTransactions(tx):
    # Reduces large tx dictionary to only pool transactions
    if 'asset-transfer-transaction' in tx:
        if pool_id == tx['asset-transfer-transaction']['asset-id']:
            return True
        else:
            return False

tx_all = []
# Get ALGO-ASA pool pairs
for i in tinypools:
    print(tinypools[i]['pair_name'])
    pool_id = tinypools[i]['pool_id']

    # Creates the tx subset for just the current pool
    pool_filter = filter(ReduceTransactions, transact_dict_all['transactions'])
    pool_dict = list(pool_filter)

    ASSET1 = tiny.fetch_asset(tinypools[i]['asset1'].id)
    ASSET2 = tiny.fetch_asset(tinypools[i]['asset2'].id)

    try:
        pool_info = tiny.fetch_pool(ASSET1, ASSET2).fetch_pool_position()
    except:
        print('Could not get current pool position. May not be in pool anymore.')

    for pool_tx in pool_dict:
        # Determine which block produced the pool tx (and mark the time)
        blockID = pool_tx['confirmed-round']
        timeofTransaction = datetime.datetime.fromtimestamp(pool_tx['round-time'])
        transact_date = algotools.ConvertDate(timeofTransaction)
        receiver = pool_tx['asset-transfer-transaction']['receiver']

        if pool_tx['asset-transfer-transaction']['amount'] == 0:
            continue # Opt-in transaction
        elif receiver == address:
            add_assets = 1
        else:
            add_assets = -1
            
        for tx in transact_dict_all['transactions']:
            # Search through txs to find how much was added to this pool
            asset_tx = {}
            if tx['confirmed-round'] == blockID:
                if tx['tx-type'] == 'pay' and tx['payment-transaction']['amount'] >= 1e4:
                    # Assumes any payment < A0.01 is a fee
                    if ASSET1 == ALGO:
                        ASSET = ASSET1
                    elif ASSET2 == ALGO:
                        ASSET = ASSET2
                    else:
                        continue
                elif tx['tx-type'] == 'axfer':
                    if ASSET1.id == tx['asset-transfer-transaction']['asset-id']:
                        ASSET = ASSET1
                    elif ASSET2.id == tx['asset-transfer-transaction']['asset-id']:
                        ASSET = ASSET2
                    else:
                        continue
                else:
                    continue

                decimals = 10 ** (-ASSET.decimals)
                
                if ASSET == ALGO:
                    asset_amount_in = (tx['payment-transaction']['amount']) * decimals
                    asset_price_in_algo = 1 # 1 algo = 1 algo
                    asset_price_now_algo = 1 # 1 algo still = 1 algo

                else:
                    asset_amount_in = (tx['asset-transfer-transaction']['amount']) * decimals
                    # Get the block for time of transaction
                    asset_price_in_algo = algotools.GetPriceFromPool(ASSET, blockID)
                    asset_price_now_algo = algotools.GetPriceFromPool(ASSET)
                    
                    if asset_price_in_algo == -1:
                        print('Not enough transactions for price data')
                        break
                
                asset_amount_now = pool_info[ASSET].amount * decimals
                asset_price_in_usd = algotools.ALGOtoUSD(asset_price_in_algo, algotools.GetPriceFromPool(USDC, blockID), algotools.GetPriceFromPool(USDT, blockID))
                asset_price_now_usd = algotools.ALGOtoUSD(asset_price_now_algo, algotools.GetPriceFromPool(USDC), algotools.GetPriceFromPool(USDT))
                
                # Save the data and add to the list
                asset_tx['pool_name'] = tinypools[i]['pair_name']
                asset_tx['asset_name'] = ASSET.name
                asset_tx['asset_id'] = ASSET.id
                asset_tx['amount_in'] = add_assets * asset_amount_in
                asset_tx['amount_now'] = asset_amount_now
                asset_tx['price_in_usd'] = add_assets * asset_price_in_usd
                asset_tx['price_in_algo'] = add_assets * asset_price_in_algo
                asset_tx['price_now_usd'] = asset_price_now_usd
                asset_tx['price_now_algo'] = asset_price_now_algo
                asset_tx['block_id'] = blockID
                asset_tx['tx_time'] = transact_date
                tx_all.append(asset_tx)

##### Calculate Gains/Losses #####
if writetofile:
    with open(filename, 'a+', newline='') as trackFile:
        writer = csv.writer(trackFile, delimiter=',',
                            quotechar='|', quoting=csv.QUOTE_MINIMAL)

        for itx in range(len(tx_all)):
            tx = tx_all[itx]

            if itx == 0 or tx['pool_name'] != tx_all[itx-1]['pool_name']:
                # Reset on first transaction or new group
                asset1_name = ''
                asset2_name = ''
                asset1_value_in = 0
                asset2_value_in = 0
                asset1_now_tot = 0
                asset2_now_tot = 0

            # Sum totals
            if asset1_name == '' and asset2_name == '':
                asset1_name = tx['asset_name']
                asset1_value_in = tx['amount_in']*tx['price_in_usd']
                asset1_value_now = tx['amount_now'] * tx['price_now_usd']
                asset1_amount_tot = tx['amount_in']
                asset1_value_hodl = asset1_amount_tot * tx['price_now_usd']
            elif tx['asset_name'] == asset1_name:
                asset1_value_in = asset1_value_in + tx['amount_in']*tx['price_in_usd']
                asset1_value_now = tx['amount_now'] * tx['price_now_usd']
                asset1_amount_tot = asset1_amount_tot + tx['amount_in']
                asset1_value_hodl = asset1_amount_tot * tx['price_now_usd']
            elif asset1_name != '' and asset2_name == '':
                asset2_name = tx['asset_name']
                asset2_value_in = tx['amount_in']*tx['price_in_usd']
                asset2_value_now = tx['amount_now'] * tx['price_now_usd']
                asset2_amount_tot = tx['amount_in']
                asset2_value_hodl = asset2_amount_tot * tx['price_now_usd']
            elif tx['asset_name'] == asset2_name:
                asset2_value_in = asset2_value_in + tx['amount_in']*tx['price_in_usd']
                asset2_value_now = tx['amount_now'] * tx['price_now_usd']
                asset2_amount_tot = asset2_amount_tot + tx['amount_in']
                asset2_value_hodl = asset2_amount_tot * tx['price_now_usd']
            
            if itx == len(tx_all)-1 or tx['pool_name'] != tx_all[itx+1]['pool_name']:
                
                # Current pool value (USD) and hodl value (Value if you did not add liquidity)
                pool_value_in = asset1_value_in + asset2_value_in
                pool_value_now = asset1_value_now + asset2_value_now
                pool_value_hodl  = asset1_value_hodl + asset2_value_hodl

                # Gain/Loss Calculation
                gain_loss = (asset1_value_now - asset1_value_in) + (asset2_value_now - asset2_value_in)

                # Impermenant loss calculation
                imp_loss = pool_value_now - pool_value_hodl

                # Print information
                print(asset1_name + ' invested value: $' + str(asset1_value_in))
                print(asset2_name + ' invested value: $' + str(asset2_value_in))
                print(asset1_name + ' current value: $' + str(asset1_value_now))
                print(asset2_name + ' current value: $' + str(asset2_value_now))
                print('Total Invested Value: $' + str(pool_value_in))
                print('Current Value: $' + str(pool_value_now))

                if gain_loss > 0:
                    print('You\'ve earned $' + str(gain_loss))
                elif gain_loss < 0:
                    print('You\'ve lost $' + str(abs(gain_loss)))
                else:
                    print('You are even. No gain or loss.')

                if imp_loss < 0:
                    print('You\'ve underperformed by $' + str(abs(imp_loss)) + ' by adding liquidity.')
                elif imp_loss > 0:
                    print('You\'ve outperformed holding by $' + str(imp_loss))
                else:
                    print('You have neither gained nor lost money by joining the pool.')

                # Now write data to csv
                if writetofile:
                    writer.writerow([datetime.datetime.now(), tx['pool_name'], 
                                    (asset1_value_in + asset2_value_in), pool_value_now, 
                                    pool_value_hodl, gain_loss, imp_loss])

if writetofile:
    print('Finished writing to csv.')
else:
    print('Did not write to csv.')