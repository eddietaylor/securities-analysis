import praw
import config
from textblob import TextBlob
from binance.client import Client
from binance.enums import *
from IPython.display import Image

### Set up Reddit API connection
reddit = praw.Reddit(
    client_id=config.REDDIT_ID,
    client_secret=config.REDDIT_SECRET,
    password=config.REDDIT_PASS,
    user_agent="USERAGENT",
    username=config.REDDIT_USER,
)
try:
    print(f"Reddit connection successful: {reddit}")
except:
    print("Reddit connection unsuccessful")

### Set up Binance paper trading client
binance_paper_client = Client(config.BINANCE_PAPER_KEY, config.BINANCE_PAPER_SECRET)
binance_paper_client.API_URL = 'https://testnet.binance.vision/api'
try:
    print(f"Binance testnet connection successful: {binance_paper_client}")
except:
    print("Binance testnet connection unsuccessful")

### Basic Scrape-Sentiment-Trade Bot
# list which will store non-zero sentiment comments
sentimentlist = []
# trailing window size for average
window = 300
# polarity threshold
threshold = 0.5

TRADE_SYMBOL = 'BTCUSDT'
# go to exchange to figure out the USD equivalent of the quantity
TRADE_QUANTITY = .0001
in_position = False


# define an average function which takes care of length 0 case
def Average(lst):
    if len(lst) == 0:
        return len(lst)
    else:
        return sum(lst[-window:])/ window

# order function. See documention in quick start section. Default to market order
def order(side, quantity, symbol, order_type=ORDER_TYPE_MARKET):
    """
    side is buy or sell
    """
    try:
        print('sending order')
        order = binance_paper_client.create_order(symbol=symbol, side=side, type=order_type,        quantity=quantity)
        print(order)
    except Exception as e:
        print('an exception has occured' + e)
        return False
    return True

# stream subreddit comments, calculate their sentiment, append to list, do trading logic
for comment in reddit.subreddit("bitcoinmarkets").stream.comments():
    print(comment.body)
    
    redditcomment = comment.body
    blob = TextBlob(redditcomment)
    #print(blob.sentiment)
    sent = blob.sentiment

    print(f"############# Sentiment is: {sent.polarity} ###############")

    # now for each comment thats read in, lets append the non-zero values to the list
    # excluding zero because its difficult for average to breach threshold
    if sent.polarity != 0:
        sentimentlist.append(sent)
        # if the threshold of polarity is met and we have enough comments
        if len(sentimentlist) > window and round(Average(sentimentlist)) > threshold:
            print("Buy")
            if in_position:
                print("######### BUY ORDER BUT WE OWN #########")
            else:
                print("######### BUY ORDER #########")
                order_succeeded = order(SIDE_BUY, TRADE_QUANTITY, TRADE_SYMBOL)
                # critical to set in_position variable to true so you don't keep buying
                # and go bankrupt
                if order_succeeded:
                    in_position = True
        elif len(sentimentlist) > window and round(Average(sentimentlist)) < -threshold:
            print("######### SELL! SELL! SELL! #########")
            if in_position:
                order_succeeded = order(SIDE_SELL, TRADE_QUANTITY, TRADE_SYMBOL)
                if order_succeeded:
                    in_position = False
            else:
                print("######### SELL BUT WE DON'T OWN BITCH #########")