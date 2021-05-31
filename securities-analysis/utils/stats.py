import math

class Welford():

    def __init__(self,a_list=None):
        self.n = 0
        self.M = 0
        self.S = 0

    def update(self,x):
        self.n += 1

        newM = self.M + (x - self.M) / self.n
        newS = self.S + (x - self.M) * (x - newM)

        self.M = newM
        self.S = newS

    @property
    def mean(self):
        return self.M

    @property
    def std(self):
        if self.n == 1:
            return 0
        return math.sqrt(self.S / (self.n - 1))
