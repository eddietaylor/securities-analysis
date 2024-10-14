from tradeAlpaca import tradeAlpaca


trade_inst = tradeAlpaca(keys_file="../../data/alpaca_keys.cfg")


print(trade_inst.get_current_price("BTC/USD", stock=False))


#print(trade_inst.get_historical_prices("GLD", "2022-06-01", "2022-06-04", freq='day'))

trade_inst.stream_data(ticker='BTC/USD', asset_class='crypto', interval_seconds=10)

