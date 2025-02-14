import sys

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
