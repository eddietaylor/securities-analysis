# **Securities Analysis**

Repo to develop securities analysis libraries driven by different schools of financial and modelling thought including technical analysis, fundamental analysis, quantitative analysis, and machine learning.

This library will possibly include a backtester as well as the ability to connect to a trading api and deploy to a cloud. This effort is currently in the research phase so the scope has not been clearly defined yet. 

## Investment Knowledge

It is recommended to have some basic understanding of investment theory, to avoid unnecessary risks, and to hopefully manage those risks. If you have no financial background, please see the [investment notes](/notebooks/notes/investments_notes.ipynb), which are largely based on Zvi Bodie's market leading textbook, *Investments*.

## Installing the dependencies

To install the dependencies to run these notebooks, you should first install [Anaconda](https://www.anaconda.com/products/individual#Downloads). 

In addition, the optimizer used in the notebooks, PyPortfolioOpt, requires C++. For Windows, install Visual Studio Build Tools and modify it to include the C++ build tools. 

Once you have installed Anaconda, run:

    conda env create -f environment.yml

to install all the dependencies into an isolated environment.

Activate the environment by running:

    conda activate securities-analysis

Update the environment with a new package by adding it in the YAML file and while in the same directory as environment.yml, activate the environment, and run:

    conda env update -f environment.yml

# **JupyterLab Cloud Server Setup**
<details>
  <summary>Expand for details</summary>
To run algorithmic trading bots, we need infrastructure which is reliable and secure. Setting up your own physical server is not necessary since we can easily rent cloud infrastructure at low cost. 

First, spin up a virtual machine at https://www.digitalocean.com/ (they call them droplets) with a minimum of 2 GB RAM. For more info on creating a production-ready server, see: https://docs.digitalocean.com/tutorials/recommended-droplet-setup/

## **SSH Encryption**

To connect to the cloud instance via ssh (we can then easily use the ssh plugin in VS Code to develop on the server), create an ssh key and add the key to the cloud instance. Follow these instructions:

https://docs.digitalocean.com/products/droplets/how-to/add-ssh-keys/

## **SSL (HTTPS) Encryption**

To create an encrypted communication between the JupyterLab server and the web browser, we set up an SSL public key and certificate. From within the cloud/cloud_deploy/ folder, run the following line from the terminal (Git Bash if on Windows):

    openssl req -x509 -nodes -days 365 -newkey rsa:2048 -keyout mykey.key -out mycert.pem

Follow the instructions and enter your location, org, name, and email details. 

For more info on SSL, see: https://www.cloudflare.com/learning/ssl/what-is-ssl/

## **Jupyter Lab Password Hashing**

It is essential to have passwords be hashed, in this case the password to the Jupyter Lab server. Hashing is a one-way function (impossible to decrypt). It is used for password validation. Still, you don't want even the hash exposed because hackers can brute force it and figure out the password (Then they would have root access to the cloud instance!!)

To generate an Argon2 hash code for the Jupyter Lab password, run the following from within the cloud/cloud_deploy/ directory:

    python jupyter_hash_code.py [your password here]

This will get copied to the cloud and set as the password authentication for the browser
login.

Luckily, Argon2 hashing is quite secure and according to one source:
"Trying to crack a volume encrypted with Argon2 created on a modern laptop would require up to 75,121 powerful machines running for ten years and cost over 4 billion dollars."

## **Browser Accessed Jupyter Lab Server Setup**

Now to copy the SSL keys and jupyter notebook config files to the cloud instance, run the dependencies install script, and launch a jupyterlab server, we simply run (within the cloud/cloud_deploy/ directory):

    bash cloud_setup.sh [public ip address of cloud instance]

Then access the server through a browser at https://[public ip address of cloud instance]:9000/lab. The password will be the one which you hashed in the step above. 

To shut down the Jupyter Lab server, from within Jupyter Lab, go to "file" then click "shutdown" (the Jupyter lab will run indefinitely at
that port until you shut it down)

## **Info On Setting Up JupyterLab Server**

https://www.digitalocean.com/community/tutorials/how-to-set-up-a-jupyterlab-environment-on-ubuntu-18-04
## **Debugging SSH Connection to Digital Ocean Droplet**

See: https://dev.to/gamebusterz/digitalocean-permission-denied-publickey-168p

SSH connection issues after rebuild: https://www.digitalocean.com/community/questions/how-can-i-get-rid-of-warning-remote-host-identification-has-changed
</details>

# **Broker API Keys and Secrets**

Preferably, your API keys should be stored as environment variables. For the Alpaca API, we want
to read the api keys from the Conda environment. To store your personal keys and secrets in the Conda environment, follow these [instructions](https://docs.conda.io/projects/conda/en/latest/user-guide/tasks/manage-environments.html#setting-environment-variables).

# **Useful Links**

Python Reddit API Wrapper: https://praw.readthedocs.io/en/stable/index.html

Python Binance API Wrapper: https://python-binance.readthedocs.io/en/latest/index.html

Python Alpaca API Wrapper: https://pypi.org/project/alpaca-trade-api/
