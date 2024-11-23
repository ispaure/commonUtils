import sys
show_verbose: bool = True


def log_msg(msg: str):
    if show_verbose:
        print(msg)


def log_exit_msg(msg: str):
    print(msg)
    sys.exit()
