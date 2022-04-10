from notebook.auth import passwd
import sys

def create_jupyter_hash_code(password):

    return print(passwd(password))

create_jupyter_hash_code(sys.argv[1])