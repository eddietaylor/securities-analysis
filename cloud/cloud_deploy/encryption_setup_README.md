# **RSA Public and Private Keys Instructions**

Run the following line from the terminal (Git Bash if on Windows):

    openssl req -x509 -nodes -days 365 -newkey rsa:2048 -keyout mykey.key -out mycert.pem

Follow instructions and enter location, org, name, and email details

# **Jupyter Hash Code Generation Instructions**

To generate a hash code for the jupyter lab password, run the following:

    python jupyter_hash_code.py "your_password_here"

Then copy this as a string into the jupyter_notebook_config.py file for the variable 
definition of c.NotebookApp.password.

# **Debugging SSH Connection to Digital Ocean Droplet**

See: https://dev.to/gamebusterz/digitalocean-permission-denied-publickey-168p