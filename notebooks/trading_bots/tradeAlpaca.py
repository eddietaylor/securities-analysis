import pandas as pd
import configparser
from datetime import datetime
import time
from alpaca.data import CryptoHistoricalDataClient, StockHistoricalDataClient
from alpaca.data import CryptoDataStream, StockDataStream
from alpaca.data.requests import StockLatestQuoteRequest, CryptoLatestQuoteRequest
from alpaca.data.requests import StockBarsRequest, CryptoBarsRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.trading.client import TradingClient
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import GetAssetsRequest
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.requests import LimitOrderRequest
from alpaca.trading.requests import StopOrderRequest
from alpaca.trading.requests import StopLimitOrderRequest
from alpaca.trading.requests import TrailingStopOrderRequest
from alpaca.trading.requests import GetOrdersRequest
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.trading.enums import OrderStatus
from alpaca.trading.enums import OrderType
from alpaca.trading.enums import AssetClass
from alpaca.trading.enums import AssetStatus
from alpaca.trading.enums import AssetExchange
from typing import Any
import asyncio
class tradeAlpaca(object):
    '''Python wrapper class for the Alpaca trading API via Alpaca-py SDK'''

    def __init__(self, keys_file):
        '''
        Parameters
        ----------
        keys_file: configuration .cfg file path
        with the following text contained within
        that file:

        [alpaca]
        api_key = laskdflasdkf
        secret_key = lskdfja;lskdfjalskdj
        endpoint = https://yoyoyoyoyoy.com
        '''
        # api key attributes
        self.config = configparser.ConfigParser()
        self.config.read(keys_file)
        self.api_key = self.config['alpaca']['api_key']
        self.secret_key = self.config['alpaca']['secret_key']
        self.endpoint = self.config['alpaca']['endpoint']
        # alpaca data clients
        self.crypto_client = CryptoHistoricalDataClient()
        self.stock_client = StockHistoricalDataClient(self.api_key, self.secret_key)
        # streaming clients
        self.crypto_stream = CryptoDataStream(self.api_key, self.secret_key)
        self.stock_stream = StockDataStream(self.api_key, self.secret_key)
        # alpaca trading client
        self.trading_client = TradingClient(self.api_key,self.secret_key, paper=True)

        self.quotes = pd.DataFrame()

    def get_current_price(self, ticker):
        '''
        Description
        -----------
        Get current price of specified instrument.

        Parameters
        ----------
        ticker (str): ticker symbol of stock or crypto
        '''
        try:
            request_params = StockLatestQuoteRequest(symbol_or_symbols=[ticker])
            latest_quote = self.stock_client.get_stock_latest_quote(request_params)
            ask = latest_quote[ticker].ask_price
            bid = latest_quote[ticker].bid_price
            time = latest_quote[ticker].timestamp
            return time, float(bid), float(ask)
        except:
            request_params = CryptoLatestQuoteRequest(symbol_or_symbols=[ticker])
            latest_quote = self.crypto_client.get_crypto_latest_quote(request_params)
            ask = latest_quote[ticker].ask_price
            bid = latest_quote[ticker].bid_price
            time = latest_quote[ticker].timestamp
            return time, float(bid), float(ask)

    def get_historical_prices(self, ticker, start, end, freq='day'):
        '''
        Description
        -----------
        Get historical prices of specified instrument

        Parameters
        ----------
        ticker (str): ticker symbol of stock or crypto
        start (str): start date, e.g. "2022-06-01"
        end (str): end date, e.g. "2022-06-04"
        freq (str): frequency (e.g. "day", "hour","minute", "month", "week")
        '''
        timeframe_dict = {'day':TimeFrame.Day, 'hour':TimeFrame.Hour, 'minute':TimeFrame.Minute, 'month':TimeFrame.Month, 'week':TimeFrame.Week}
        try:
            request_params = StockBarsRequest(
                        symbol_or_symbols=[ticker],
                        timeframe=timeframe_dict[freq],
                        start=datetime.strptime(start, '%Y-%m-%d'),
                        end=datetime.strptime(end, '%Y-%m-%d')
                 )
            bars = self.stock_client.get_stock_bars(request_params)
            bars_df = bars.df
            return bars_df
        except:
            request_params = CryptoBarsRequest(
                        symbol_or_symbols=[ticker],
                        timeframe=timeframe_dict[freq],
                        start=datetime.strptime(start, '%Y-%m-%d'),
                        end=datetime.strptime(end, '%Y-%m-%d')
                 )
            bars = self.crypto_client.get_crypto_bars(request_params)
            bars_df = bars.df
            return bars_df

    async def quote_data_handler(self, data: Any):
        #print(type(data))
        # the type is alpaca.data.models.quotes.Quote (look up in docs)
        self.quotes = self.quotes.append({'timestamp':data.timestamp, 'symbol':data.symbol, 'ask_price':data.ask_price, 'bid_price':data.bid_price}, ignore_index=True)

        # write the last row of self.qutoes to a csv file in append mode
        self.quotes.tail(1).to_csv('data.csv', mode='a', header=False)
        #print(f"yo the data is getting stored: {self.quotes}")


    def stream_data(self, ticker, asset_class=None):
        '''
        Description
        -----------
        stream the data (NEEDS MORE WORK. WORKS FROM .py FILE)

        Parameters
        ----------
        asset_class (str): Which asset class this ticker belongs to (e.g. 'equity','crypto')
        '''
        try:
            if asset_class == 'equity':
                wss_client = StockDataStream(self.api_key, self.secret_key)
                wss_client.subscribe_quotes(self.quote_data_handler, ticker)
                wss_client.run()
            elif asset_class == 'crypto':
                wss_client = CryptoDataStream(self.api_key, self.secret_key)
                wss_client.subscribe_quotes(self.quote_data_handler, ticker)
                wss_client.run()
                # run for a user specificed amount of time
                # asyncio.sleep(3)
                # wss_client.close()
        except Exception as e:
            print(e)
    
    def get_account_details(self):
        '''
        Description
        -----------
        Returns account details like buying power,
        equity, etc.
        '''
        #trading_client = TradingClient(self.api_key, self.secret_key, paper=True)
        account = self.trading_client.get_account()
        return account

    def get_available_assets(self, asset_class='equity', status='active', exchange='nyse'):
        '''
        Description
        -----------
        Get assets available for trading with Alpaca
        
        Parameters
        ----------
        class (str): either 'equity' or 'crypto'
        status (str): avalable for trading? either 'active' or 'inactive'
        exchange (str): which exchange? 'amex', 'arca', 'bats', 'nyse', 
        'nasdaq', 'nysearca', 'ftxu', 'cbse', 'gnss', 'ersx', 'otc'
        '''
        class_dict = {'equity':AssetClass.US_EQUITY, 'crypto':AssetClass.CRYPTO}
        active_dict = {'active':AssetStatus.ACTIVE, 'inactive':AssetStatus.INACTIVE}
        exchange_dict = {'amex':AssetExchange.AMEX, 'arca':AssetExchange.ARCA, 
        'bats':AssetExchange.BATS, 'nyse':AssetExchange.NYSE, 'nasdaq':AssetExchange.NASDAQ,
        'nysearca':AssetExchange.NYSEARCA, 'ftxu':AssetExchange.FTXU, 'cbse':AssetExchange.CBSE,
        'gnss':AssetExchange.GNSS, 'ersx':AssetExchange.ERSX, 'otc':AssetExchange.OTC}

        #trading_client = TradingClient(self.api_key,self.secret_key, paper=True)
        # search for crypto assets
        search_params = GetAssetsRequest(asset_class=class_dict[asset_class], 
                                        status=active_dict[status], 
                                        exchange=exchange_dict[exchange])

        assets = self.trading_client.get_all_assets(search_params)

        if len(assets) > 0:
            assets_df = pd.DataFrame.from_records([dict(i) for i in assets], index = [i for i in range(len(assets))])
            return assets_df
        else:
            print("no data")

    #TODO: what are the safest defaults for the below params?
    def create_order(self, ticker, units, qty_price=None, order_type=None, 
                    limit_price=None, stop_price=None, trail_price=None, trail_perc=None,
                    side=None, time_in_force=None):
        '''
        Description
        -----------
        Create either market order, limit order, stop order, stop limit order or trailing stop order
        TODO: Bracket Orders, OCO Orders, OTO Orders
        more info at: https://alpaca.markets/docs/trading/orders/.
        Also see: https://www.schwab.com/learn/story/3-order-types-market-limit-and-stop-orders
        Keep in mind price gaps (off hour shifts in supply and demand
        due to earnings announcements, analyst's opinion change, news release).

        Parameters
        ----------
        ticker (str): ticker symbol
        units (float): number of shares to trade
        qty_price (float): dollar value of shares to trade 
        (only works with market orders. maybe limit?)
        order_type (str): type of order. e.g. 'market', 'limit', 'stop', 'stop_limit', 'trailing_stop'
        limit_price (float): limit price (hurdle for sell and the limbo for buy)
        stop_price (float): stop price (pass this point and it becomes market order 
        and executes next available price)
        trail_price (float): dollar value away from highest water mark (cum max since order submitted). 
        e.g. for sell trailing stop, stop price is hwm - trail_price. (TODO: implement)
        trail_perc (float): percent value away from hwm. 
        side (str): buy or sell? e.g. 'buy', 'sell'.
        time_in_force (str): time constraints of order (e.g. 'day', 'ioc')
        
        Order Type Parameter Requirements
        ---------------------------------
        order_type = 'market' -> ticker, (units or qty_price), side, time_in_force

        order_type = 'limit' -> ticker, limit_price, units, side, time_in_force

        order_type = 'stop' -> ticker, stop_price, units, side, time_in_force

        order_type = 'stop_limit' -> ticker, stop_price, limit_price, units, side, time_in_force
        
        order_type = 'trailing_stop' -> ticker, trail_perc, units, side, time_in_force

        Time in Force Descriptions
        --------------------------
        Note: only 'ioc' and 'gtc' supported for crypto
        time_in_force = 'day': day order only valid 9:30am - 4:00pm and cancelled if unfilled 
        by the end of day. IF SUBMITTED AFTER CLOSE, IT IS QUEUED AND SUBMITTED FOLLOWING DAY.
        time_in_force = 'ioc': Immediate or Cancel (all or part of the order needs to be filled)
        time_in_force = 'gtc': Good til Cancelled

        Notes on Order Types
        --------------------
        order_type = 'stop': The danger with these is price gaps i.e. price can jump for a variety of reasons.
        and you can take bigger loss than you intended (hence we have the stop limit)
        But stop order is better in volatile market when "getting out" is the priority
        see: https://www.schwab.com/learn/story/trading-up-close-stop-and-stop-limit-orders
        and: https://www.investopedia.com/articles/trading/05/playinggaps.asp
        '''
        #trading_client = TradingClient(self.api_key,self.secret_key, paper=True)
        buy_sell_dict = {'buy':OrderSide.BUY, 'sell':OrderSide.SELL}
        time_force_dict = {'day':TimeInForce.DAY, 'gtc':TimeInForce.GTC, 'ioc':TimeInForce.IOC}
        order_type_dict = {'market':OrderType.MARKET, 'limit':OrderType.LIMIT, 
                           'stop':OrderType.STOP, 'stop_limit':OrderType.STOP_LIMIT, 
                           'trailing_stop':OrderType.TRAILING_STOP}

        if order_type == 'market' and qty_price==None:
            # market order trade in units of number of shares
            market_order_data = MarketOrderRequest(
                                symbol=ticker,
                                qty=units,
                                side=buy_sell_dict[side],
                                time_in_force=time_force_dict[time_in_force]
                                )
            # Market Order
            market_order = self.trading_client.submit_order(
                            order_data=market_order_data
                        )
        elif order_type == 'market' and qty_price is not None:
            # market order trade in units of currency
            market_order_data = MarketOrderRequest(
                                symbol=ticker,
                                notional=qty_price,
                                side=buy_sell_dict[side],
                                time_in_force=time_force_dict[time_in_force]
                                )
            # Market Order
            market_order = self.trading_client.submit_order(
                            order_data=market_order_data
                        )
        elif order_type == 'limit':
            limit_order_data = LimitOrderRequest(
                    symbol=ticker,
                    limit_price=limit_price,
                    qty=units, #how much of the share you trade 
                    side=buy_sell_dict[side],
                    time_in_force=time_force_dict[time_in_force]
                   )
            # Limit Order
            limit_order = self.trading_client.submit_order(
                            order_data=limit_order_data
                        )
        elif order_type == 'stop':
            stop_order_data = StopOrderRequest(
                    symbol=ticker,
                    stop_price=stop_price,
                    qty=units,
                    side=buy_sell_dict[side],
                    time_in_force=time_force_dict[time_in_force],
                    type=order_type_dict[order_type] # look into this. you specify the order type?
                   )
            # Stop Order
            stop_order = self.trading_client.submit_order(
                            order_data=stop_order_data
                        )
        elif order_type == 'stop_limit':
            # can save you from the danger of price gaps but you can be screwed if price
            # falls even further. Not good for volatile market but good for end of hours
            # see the Schwab link above. 
            # also see: https://alpaca.markets/docs/trading/orders/#stop-limit-order
            stop_limit_order_data = StopLimitOrderRequest(
                    symbol=ticker,
                    stop_price=stop_price,
                    limit_price=limit_price,
                    qty=units,
                    side=buy_sell_dict[side],
                    time_in_force=time_force_dict[time_in_force],
                    type='stop_limit' # look into this. you specify the order type
                   )
            # Stop Limit Order
            stop_limit_order = self.trading_client.submit_order(
                            order_data=stop_limit_order_data
                        )
        elif order_type == 'trailing_stop':
            # need to make sure difference between trailing stop 
            # and price is big enough such that typical fluctuations
            # do no trigger premature execution
            trailing_stop_order_data = TrailingStopOrderRequest(
                    symbol=ticker,
                    trail_percent=trail_perc,
                    qty=units,
                    side=buy_sell_dict[side],
                    time_in_force=time_force_dict[time_in_force],
                    type='trailing_stop' # look into this. you specify the order type
                   )
            # Trailing Stop Order
            trailing_stop_order = self.trading_client.submit_order(
                            order_data=trailing_stop_order_data
                        )

    def get_orders(self, status='all', side='all'):
        '''
        Description
        -----------
        Get all orders associated with the account. 

        Parameters
        ----------
        status (str): order status (e.g. "open", "closed", "all")
        side (str): buy or sell orders (e.g. "buy", "sell", "all")
        '''

        if side == 'all':
            # params to filter orders by
            request_params = GetOrdersRequest(
                                status=status

                            )
        else:
            request_params = GetOrdersRequest(
                                status=status,
                                side=side
                            )
        # orders that satisfy params
        orders = self.trading_client.get_orders(filter=request_params)
        # order history dataframe
        if len(orders) > 0:
            order_hist_df = pd.DataFrame.from_records([dict(i) for i in orders], index = [i for i in range(len(orders))])
            return order_hist_df
        else:
            print("NO ORDERS TO RETURN")

    def cancel_all_orders(self):
        '''
        Description
        -----------
        Cancel all orders (cancellation of an order not guaranteed)
        '''
        # attempt to cancel all open orders
        cancel_statuses = self.trading_client.cancel_orders()
        print("INITIATED ATTEMPT TO CANCEL ALL ORDERS") 

    def get_all_positions(self):
        '''
        Description
        -----------
        Get all open positions in your portfolio
        '''
        positions = self.trading_client.get_all_positions()
        if len(positions) > 0:
            positions_df = pd.DataFrame.from_records([dict(i) for i in positions], index = [i for i in range(len(positions))])
            return positions_df
        else:
            print("NO POSITIONS")

    def close_all_positions(self, cancel_orders=True):
        '''
        Description
        -----------
        Close all open positions

        Parameters
        ----------
        cancel_orders (Bool): Whether to cancel open orders too.
        '''
        self.trading_client.close_all_positions(cancel_orders=cancel_orders)
