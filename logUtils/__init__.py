# ----------------------------------------------------------------------------------------------------------------------
# AUTHORSHIP INFORMATION - THIS FILE BELONGS TO MARC-ANDRE VOYER HELPER FUNCTIONS CODEBASE

__author__ = 'Marc-André Voyer'
__copyright__ = 'Copyright (C) 2020-2026, Marc-André Voyer'
__license__ = "MIT License"
__maintainer__ = 'Marc-André Voyer'
__email__ = 'marcandre.voyer@gmail.com'
__status__ = 'Production'

# ----------------------------------------------------------------------------------------------------------------------
# IMPORTS

import sys


# ----------------------------------------------------------------------------------------------------------------------
# CODE

show_verbose: bool = True


def log_msg(msg: str):
    if show_verbose:
        print(msg)


def exit_msg(msg: str):
    print(msg)
    sys.exit()


def join(lst):
    value_lst = []
    for value in lst:
        value_lst.append(str(value))
    return ", ".join(value_lst)
