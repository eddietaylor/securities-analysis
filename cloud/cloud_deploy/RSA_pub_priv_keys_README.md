# **RSA Public and Private Keys Instructions**

Run the following line from the terminal (Git Bash if on Windows):

    openssl req -x509 -nodes -days 365 -newkey rsa:2048 -keyout mykey.key -out mycert.pem

Follow instructions and enter location, org, name, and email details