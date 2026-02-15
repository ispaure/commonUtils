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


"""
Functions to read through a (.ini) file.
"""

from typing import *
from pathlib import Path
import configparser

# Common utilities
from . import fileUtils
from .debugUtils import *


# ----------------------------------------------------------------------------------------------------------------------
# DEBUG

show_verbose = False


# ----------------------------------------------------------------------------------------------------------------------
# CODE


def config_section_map(cfg_file_path: Union[str, Path], section, variable, bypass_error=False):
    """
    Retrieve a value from a section of a config file.
    :param cfg_file_path: Path to the config file to look into
    :param section: Name of section in which the value you want is found
    :type section: str
    :param variable: Name of the value you want to get as return
    :type variable: str
    :param bypass_error: Cheap way to read from cfg file, unorthodox. Do if needed for files with errors
    :type bypass_error: bool
    :rtype: str
    """
    tool_name = 'config_section_map'

    # REGULAR APPROVED METHOD
    if not bypass_error:
        # Read the config file
        config = configparser.ConfigParser()
        try:
            with open(cfg_file_path, 'r', encoding='utf-8-sig') as f:
                config.read_file(f)
        except Exception as e:
            log(Severity.ERROR, tool_name, f"Error reading config file: {e}")
            return None

        # Retrieve dictionary of the section
        dict1 = {}
        try:
            options = config.options(section)
            for option in options:
                try:
                    dict1[option] = config.get(section, option)
                    if dict1[option] == -1:
                        log(Severity.ERROR, tool_name, "skip: %s" % option)
                except Exception as e:
                    log(Severity.ERROR, tool_name, f"Exception on {option}: {e}")
                    dict1[option] = None
        except Exception as e:
            log(Severity.ERROR, tool_name, f"Error accessing section '{section}': {e}")
            return None

        # Return the requested variable
        return dict1.get(variable)

    # UNORTHODOX METHOD TO USE IF CONFIG FILE IS BROKEN
    else:
        # Var to search for
        section_line = f'[{section}]'
        var_line_type_a = f'{variable} = '
        var_line_type_b = f'{variable}='

        line_lst = fileUtils.read_file(cfg_file_path)
        right_section = False
        for line in line_lst:
            if line == section_line:
                right_section = True
            else:
                if right_section:
                    if line.startswith(var_line_type_a):
                        return line.split(' = ')[-1]
                    elif line.startswith(var_line_type_b):
                        return line.split('=')[-1]
                    elif line.startswith('['):
                        break
        return None


def config_add_variable(cfg_file_path, section, variable, value):
    """
    Expects variable to not be there already.
    Adds a variable to a config file and sets its value. If required, add its section.
    :param section: Expected section for value
    :type section: str
    :param variable: Variable to create in section
    :type variable: str
    :param value: Value for the variable
    :type value: str
    :param cfg_file_path: Path of the config file
    :type cfg_file_path: Union[str, Path]
    """

    # Read the lines from the config file and store in a list
    lines_lst = fileUtils.read_file(cfg_file_path)

    if len(lines_lst) > 1:
        if ' = ' in lines_lst[1]:
            equal_format = ' = '
        else:
            equal_format = '='
    else:
        equal_format = ' = '

    # Make new lines to add
    section_line = f'[{section}]'
    variable_line_to_add = f'{variable}{equal_format}{value}'

    # See if the section is already there
    section_is_there = False
    for line in lines_lst:
        if line == section_line:
            section_is_there = True
            break

    # Make list for new lines
    new_lines_lst = []

    # If section was there, add a line after the section with new variable and value
    if section_is_there:
        for line in lines_lst:
            new_lines_lst.append(line)
            if line == section_line:
                new_lines_lst.append(variable_line_to_add)
    else:
        # Add the existing lines first
        new_lines_lst = lines_lst
        # At the end, add the new section
        new_lines_lst.append('\n' + section_line)
        # After, add its variable and value
        new_lines_lst.append(variable_line_to_add)

    # Write the result to the file
    file = open(cfg_file_path, 'w')
    for line in new_lines_lst:
        file.write(line + '\n')
    file.close()


def config_set_variable(cfg_file_path, section, variable, value):
    """
    Expects file to already have the section and variable. It just needs to be set to new value
    """

    # Read the lines from the config file and store in a list
    lines_lst = fileUtils.read_file(cfg_file_path)

    # Make list for new lines
    new_lines_lst = []

    # Determine key lines
    section_line = '[{section}]'.format(section=section)
    var_line_type_a = f'{variable} = '
    var_line_type_b = f'{variable}='

    in_good_section = False
    for line in lines_lst:
        line_appended_this_round = False
        if section_line in line:
            in_good_section = True
        if in_good_section:
            if line.startswith(var_line_type_a):
                new_lines_lst.append(f'{variable} = {value}')
                in_good_section = False
                line_appended_this_round = True
            elif line.startswith(var_line_type_b):
                new_lines_lst.append(f'{variable}={value}')
                in_good_section = False
                line_appended_this_round = True
        if not line_appended_this_round:
            new_lines_lst.append(line)

    # Write the result to the file
    file = open(cfg_file_path, 'w')
    for line in new_lines_lst:
        file.write(line + '\n')
    file.close()


def config_set_add_variable(cfg_file_path, section, variable, value):
    """
    Don't know if something is there already, add if not else set
    """
    tool_name = 'config_set_add_variable'
    return_val = config_section_map(cfg_file_path, section, variable, bypass_error=True)
    if show_verbose:
        log(Severity.DEBUG, tool_name, f'Return Value: "{return_val}"')
    if return_val is None:
        if show_verbose:
            log(Severity.DEBUG, tool_name, 'Variable is None, adding variable...')
        config_add_variable(cfg_file_path, section, variable, value)
    else:
        if show_verbose:
            log(Severity.DEBUG, tool_name, 'Variable exists, setting variable...')
        config_set_variable(cfg_file_path, section, variable, value)


def config_remove_section(cfg_file_path, section):
    """
    Remove a section from a config file
    """
    tool_name = 'config_remove_section'
    line_lst = fileUtils.read_file(cfg_file_path)
    new_line_lst = []
    section_str = f'[{section}]'
    in_right_section = False
    for line in line_lst:
        if line.startswith(section_str):
            in_right_section = True
        elif not in_right_section:
            new_line_lst.append(line + '\n')
        else:
            if line.startswith('['):
                in_right_section = False
                new_line_lst.append(line + '\n')

    fileUtils.write_file(cfg_file_path, new_line_lst)

