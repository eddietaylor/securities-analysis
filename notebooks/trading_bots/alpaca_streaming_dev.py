#!/usr/bin/env python
# coding: utf-8

# In[1]:


from tradeAlpaca import tradeAlpaca


# In[2]:


trade_inst = tradeAlpaca(keys_file="../../data/alpaca_keys.cfg")


# In[ ]:


trade_inst.stream_data(ticker='BTC/USD', asset_class='crypto')

