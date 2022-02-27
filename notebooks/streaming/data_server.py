import zmq
import math
import time
import random

# using publisher-subscriber (PUB-SUB) pattern
context = zmq.Context()
socket = context.socket(zmq.PUB)
socket.bind('tcp://0.0.0.0:5555')

class InstrumentPrice(object):
    def __init__(self):
        self.symbol = 'ET'
        self.t = time.time()
        self.value = 100.
        self.sigma = 0.4
        self.r = 0.01

    def simulate_value(self):
        ''' generate new random price
        '''
        t = time.time()
        # normalize to a year of trading seconds
        dt = (t - self.t) / (252 * 8 * 60 * 60)
        self.t = t
        # euler scheme for geometric Brownian motion
        self.value *= math.exp((self.r - 0.5 * self.sigma ** 2) * dt + \
        self.sigma * math.sqrt(dt) * random.gauss(0,1))

        return self.value

#instantiate
ip = InstrumentPrice()

while True:
    msg = f"{ip.symbol}, {ip.simulate_value()}"
    print(msg)
    socket.send_string(msg)
    time.sleep(random.random() * 2)