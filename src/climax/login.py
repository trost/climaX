#!/usr/bin/env python
# Author: Arne Neumann

"""
This module handles the connection to the MySQL database.

To connect to the database, you'll need a file containing your login
credentials called 'login.yaml'. In case you don't have one, see
'login.yaml.example' for an example of such a file.
"""

import os

import MySQLdb
import yaml

CONFIG_FILE = open(os.path.expanduser('~/.climax.yaml'), 'r')
CONFIG = yaml.load(CONFIG_FILE)

def get_db(host=CONFIG['host'], user=CONFIG['user'],
           passwd=CONFIG['passwd'], db=CONFIG['db']):
    return MySQLdb.connect(host, user, passwd, db)

if __name__ == '__main__':
    print get_db()
