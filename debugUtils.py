import sys
import enum
from datetime import datetime

# Settings
include_time = False
verbose_debug = True


def print_debug_msg(msg, show_verbose):
    if show_verbose:
        print(msg)


def exit_msg(msg):
    print(msg)
    sys.exit()


class Severity(enum.Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class DebugLogger:
    def __init__(self, log_file="debug.log"):
        self.log_file = log_file

    def log_debug(self, severity: Severity, title: str, message: str):
        if severity == Severity.DEBUG and not verbose_debug:
            return

        # Format the log message
        if include_time:
            timestamp = datetime.now().strftime("%H:%M:%S")
            skip_char = ' '
        else:
            timestamp = ''
            skip_char = ''

        full_message = f"{timestamp}{skip_char}[{severity.value}] {title}: {message}"

        # line skips always put text a bit further on line
        num_spaces = len(timestamp) + len(f'{severity.value}') + len(title) + 5 + len(skip_char)
        space_str = ' ' * num_spaces
        full_message = full_message.replace('\n', f'\n{space_str}')
        # if '\n' in full_message:
        #     full_message += '\n'

        # Format color
        match severity:
            case Severity.DEBUG:
                colored_msg = f'\033[35m{full_message}\033[0m'
            case Severity.INFO:
                colored_msg = full_message
            case Severity.WARNING:
                colored_msg = f'\033[33m{full_message}\033[0m'
            case Severity.ERROR:
                colored_msg = f'\033[31m{full_message}\033[0m'
            case Severity.CRITICAL:
                colored_msg = f'\033[41;37m{full_message}\033[0m'
            case _:
                colored_msg = full_message

        # Print to console
        print(colored_msg)

        # Append to log file
        with open(self.log_file, "a") as log:
            log.write(full_message + "\n")


# Create a singleton instance of the logger
logger_instance = DebugLogger()

# Alias for the log_debug method
log = logger_instance.log_debug
