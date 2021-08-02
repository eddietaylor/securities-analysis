# securities-analysis

Repo to develop securities analysis libraries driven by different schools of financial and modelling thought including technical analysis, fundamental analysis, quantitative analysis, and machine learning.

This library will possibly include a backtester as well as the ability to connect to a trading api and deploy to a cloud. This effort is currently in the research phase so the scope has not been clearly defined yet. 

## Installing the dependencies

To install the dependencies to run these notebooks, you can use [Anaconda](https://www.anaconda.com/products/individual#Downloads). Once you have installed Anaconda, run:

    conda env create -f environment.yml

to install all the dependencies into an isolated environment.

Activate the environment by running:

    conda activate securities-analysis

Update the environment with a new package by adding it in the YAML file and while in same directory as environment.yml, activate the environment, and run:

    conda env update -f environment.yml

## Useful Links

Python Reddit API Wrapper: https://praw.readthedocs.io/en/stable/index.html

Python Binance API Wrapper: https://python-binance.readthedocs.io/en/latest/index.html
