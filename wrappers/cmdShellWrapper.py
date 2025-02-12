import subprocess
import time
from typing import *
from pathlib import Path
import commonUtils.fileUtils as fileUtils
from commonUtils.debugUtils import *

show_verbose = False


def delete_script_file(file_path):
    # Delete script file if exists. Returns false if could not delete
    if os.path.exists(file_path):
        os.remove(file_path)
        if os.path.exists(file_path):
            print('Could not remove properly, do NOT continue with sync')
            return False
    return True


def should_use_shell(command):
    """Decide whether to use shell=True based on command and OS"""
    if fileUtils.get_os() == 'Windows' or fileUtils.get_os() == 'macOS':  # TODO: Added macOS back here to patch up, idk if want this!
        return True  # Windows prefers shell=True for most cases
    elif isinstance(command, list):
        return False  # List commands always work with shell=False
    elif any(symbol in command for symbol in ["|", ">", "&", ";"]):
        return True  # Linux/macOS shell syntax requires shell=True
    else:
        return False


def exec_cmd(command, wait_for_output=True, in_new_window: Union[None, str, Path] = None):
    """
    Execute command from CMD shell (Windows) or the terminal (MacOS & Linux)
    :param command: Command to execute
    :type command: str
    :return: List of lines are returned
    :rtype: lst of str
    """

    def terminate_p_open(p_open_to_close):
        """
        Close Popen subprocess
        :param p_open_to_close: Popen to close
        :type p_open_to_close: subprocess.Popen
        """
        p_open_to_close.stderr.close()
        p_open_to_close.stdout.close()
        if p_open_to_close.stdin is not None:
            p_open_to_close.stdin.close()

    def clean_output_line(line_str):
        """
        Clean output lines so they only keep relevant information.
        """
        decoded_line = line_str.decode()
        cleaned_line = decoded_line.rstrip('\n')  # Remove n from end of line
        cleaned_line = cleaned_line.rstrip('\r')  # Remove r from end of line
        print_debug_msg(cleaned_line, show_verbose)  # Print line (if debug)
        return cleaned_line

    # If code must be executed in new cmd window
    if in_new_window is not None:
        # If to open in new window, write commands in bat file and launch bat file.
        match fileUtils.get_os():
            case 'Windows':
                # Will need to write to file and launch that with script instead
                sync_file_path = str(in_new_window)
                # Delete existing file at path
                result = delete_script_file(sync_file_path)
                if not result:
                    return False
                # Write command to file
                command = command.replace('&', '&&')
                command = command.replace('%', '%%')
                fileUtils.write_file(sync_file_path, command)
                # Replace command by command to open previously written file
                command = 'start ' + sync_file_path
            # If to open in new window, reformat command for Ubuntu (Linux)

            case 'Linux':
                # TODO: Launching in new window does not work on Linux currently, for some reason! Even though running this command through the terminal works.
                command = f'gnome-terminal -- bash -c "{command}; exec bash"'

            # If to open in new window, reformat command for macOS
            case 'macOS':
                macos_cmd_in_new_window = "osascript -e 'tell app \"Terminal\" to do script \"{}\"'"
                command = macos_cmd_in_new_window.format(command.replace('"', '\\"'))

            case _:
                log(Severity.CRITICAL, 'cmdShellWrapper', 'Platform not supported!')
                return

    # Time out value (in milliseconds)
    time_out = 15

    # If debug, print command that was sent
    print_debug_msg('Initiating Execute Shell Command procedure.', show_verbose)
    print_debug_msg('Command to send:', show_verbose)
    print_debug_msg(command, show_verbose)

    # Should use shell?
    use_shell = should_use_shell(command)

    # Open subprocess, until all output is received.
    p_open = subprocess.Popen(command,
                              shell=use_shell,  # In case of doubt, this used to be set to always true before doing linux stuff!
                              stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE,
                              stdin=None)

    # Run loop for as long as receive new lines
    output_lines = []
    loop_begin_time = time.time()
    stdout_lst = []
    stderr_lst = []

    if wait_for_output:
        while True:
            # Status, whether it's finished shelling out results or not.
            status = p_open.poll()
            p_open.stdout.flush()

            # Standard output
            stdout = p_open.stdout.readlines()
            # Standard error
            stderr = p_open.stderr.readlines()

            if len(stdout) > 0:
                stdout_lst += stdout
            if len(stderr) > 0:
                stderr_lst += stderr

            # There is new output. Reset counter to current time.
            if stderr or stdout:
                loop_begin_time = time.time()

            # If finished
            if status is not None:  # When status is not None, has finished sending results.
                output_lines = stdout_lst + stderr_lst
                terminate_p_open(p_open)  # Terminate open process
                break

            # If took too long, break off from the while loop
            now = time.time()
            if now - loop_begin_time > time_out:
                terminate_p_open(p_open)
                break

    # If debug, print result
    print_debug_msg('Output lines:', show_verbose)

    # Clean the output lines
    output_lines_cleaned = []
    for line in output_lines:
        output_lines_cleaned.append(clean_output_line(line))  # Append clean line to result

    # Return result
    return output_lines_cleaned
