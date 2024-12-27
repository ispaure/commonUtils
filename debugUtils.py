import sys


def print_debug_msg(msg, show_verbose):
    if show_verbose:
        print(msg)


def exit_msg(msg):
    print(msg)
    sys.exit()
