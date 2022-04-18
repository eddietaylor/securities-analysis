# **JupyterLab Cloud Server Setup**

First, spin up a virtual machine at https://www.digitalocean.com/ (they call them droplets) with a minimum of 2 GB RAM. 

## **SSH Encryption**

To connect to the cloud instance via ssh (we can then easily use the ssh plugin in VS Code to develop on the server), create an ssh key and add the key to the cloud instance. Follow these instructions:

https://docs.digitalocean.com/products/droplets/how-to/add-ssh-keys/

## **SSL (HTTPS) Encryption**

To create an encrypted communication between the JupyterLab server and the web browser, we set up an SSL public key and certificate. Run the following line from the terminal (Git Bash if on Windows):

    openssl req -x509 -nodes -days 365 -newkey rsa:2048 -keyout mykey.key -out mycert.pem

Follow instructions and enter your location, org, name, and email details. 

For more info on SSL, see: https://www.cloudflare.com/learning/ssl/what-is-ssl/

## **Jupyter Lab Password Hashing**

It is essential to have passwords be hashed. Hashing is a one-way function (impossible to decrypt). It is used for password validation. Still, you don't want even the hash exposed because hackers can brute force it and figure out the password (Then they would have root access to the cloud instance!!)

To generate an Argon2 hash code for the Jupyter Lab password, run the following:

    python jupyter_hash_code.py [your password here]

This will get copied to the cloud and set as the password authentication for the browser
login.

Luckily, Argon2 hashing is quite secure and according to one source:
"Trying to crack a volume encrypted with Argon2 created on a modern laptop would require up to 75,121 powerful machines running for ten years and cost over 4 billion dollars."

## **Browser Accessed Jupyter Lab Server Setup**

Now we the copy SSL keys and jupyter notebook config files to the cloud instance, run the dependencies install script, and launch a jupyterlab server by simply running:

    bash cloud_setup.sh [public ip address of cloud instance]

Then access the server through a browser at https://[public ip address of cloud instance]:9000/lab. The password will be the one which you hashed in the step above. 

To shut down the Jupyter Lab server, from within Jupyter Lab, go to "file" then click "shutdown" (the Jupyter lab will run indefinitely at
that port until you shut it down)

## **Info On Setting Up JupyterLab Server**

https://www.digitalocean.com/community/tutorials/how-to-set-up-a-jupyterlab-environment-on-ubuntu-18-04
## **Debugging SSH Connection to Digital Ocean Droplet**

See: https://dev.to/gamebusterz/digitalocean-permission-denied-publickey-168p

