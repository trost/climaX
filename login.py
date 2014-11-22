#!/usr/bin/env python
# Author: Arne Neumann

"""This is a mock replacement of the missing login module"""


def get_db():
    return FakeDatabaseObject()


class FakeDatabaseObject(object):
    def __init__(self):
        pass
    def cursor(self):
        return FakeCursor()


class FakeCursor(object):
    def __init__(self):
        pass
    def execute(self, arg1):
        pass
    def fetchall(self):
        return []


