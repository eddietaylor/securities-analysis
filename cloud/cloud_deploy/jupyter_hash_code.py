from notebook.auth import passwd
import configparser
import sys

def create_jupyter_hash_code(password):

    hash_pass = passwd(password)

    config = configparser.ConfigParser()
    config['jupyterlabserver'] = {}
    config['jupyterlabserver']['hash_password'] = f"{hash_pass}"
    with open('../../data/hash.cfg', 'w') as configfile:
        config.write(configfile)

    return print("hashed password generated and stored")

create_jupyter_hash_code(sys.argv[1])