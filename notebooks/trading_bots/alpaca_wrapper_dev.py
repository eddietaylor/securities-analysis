#!/usr/bin/env python
# coding: utf-8

# ### **Alpaca API Python Wrapper**

# In[8]:


import configparser
from datetime import datetime
import time
from alpaca.data import CryptoHistoricalDataClient, StockHistoricalDataClient
from alpaca.data import CryptoDataStream, StockDataStream
from alpaca.data.requests import StockLatestQuoteRequest, CryptoLatestQuoteRequest
from alpaca.data.requests import StockBarsRequest, CryptoBarsRequest
from alpaca.data.timeframe import TimeFrame
from typing import Any
import asyncio
#from tradeAlpaca import tradeAlpaca


# In[30]:


class tradeAlpaca(object):
    '''python wrapper class for alpaca trading API'''

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

    def get_current_price(self, ticker):
        '''
        gets current price of specified instrument
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
        gets historical prices of specified instrument
        parameters
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
        print(data)

    def stream_data(self, ticker):
        '''
        stream the data
        '''
        
        try:
            wss_client = StockDataStream(self.api_key, self.secret_key)
            wss_client.subscribe_quotes(self.quote_data_handler, ticker)
            wss_client.run()
        except:
            wss_client = CryptoDataStream(self.api_key, self.secret_key)
            wss_client.subscribe_quotes(self.quote_data_handler, ticker)
            wss_client.run()
    


# In[31]:


trade_inst = tradeAlpaca(keys_file="../../data/alpaca_keys.cfg")


# In[32]:


trade_inst.get_current_price('SPY')


# In[33]:


trade_inst.get_historical_prices("BTC/USD", start="2022-01-01", end="2022-10-28").head()


# In[34]:


# ONLY WORKS FROM .py file!!!
#trade_inst.stream_data("BTC/USD")

