"""
Functions to read through a (.ini) file.
"""

import configparser
from commonUtils import fileUtils
from typing import *
from pathlib import Path


# ----------------------------------------------------------------------------------------------------------------------
# AUTHORSHIP INFORMATION

__author__ = 'Marc-André Voyer'
__copyright__ = 'Copyright (C) 2020-2022, Marc-André Voyer'
__license__ = "GNU General Public License"
__maintainer__ = 'Marc-André Voyer'
__email__ = 'marcandre.voyer@gmail.com'
__status__ = 'Development'


# ----------------------------------------------------------------------------------------------------------------------
# DEBUG

show_verbose = True


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

    # REGULAR APPROVED METHOD
    if not bypass_error:
        # Read the config file
        config = configparser.ConfigParser()
        try:
            with open(cfg_file_path, 'r', encoding='utf-8-sig') as f:
                config.read_file(f)
        except Exception as e:
            print(f"Error reading config file: {e}")
            return None

        # Retrieve dictionary of the section
        dict1 = {}
        try:
            options = config.options(section)
            for option in options:
                try:
                    dict1[option] = config.get(section, option)
                    if dict1[option] == -1:
                        print("skip: %s" % option)
                except Exception as e:
                    print(f"Exception on {option}: {e}")
                    dict1[option] = None
        except Exception as e:
            print(f"Error accessing section '{section}': {e}")
            return None

        # Return the requested variable
        return dict1.get(variable)

    # UNORTHODOX METHOD TO USE IF CONFIG FILE IS BROKEN
    else:
        line_lst = fileUtils.read_file(cfg_file_path)
        right_section = False
        for line in line_lst:
            if line == f'[{section}]':
                right_section = True
            else:
                if right_section:
                    if line.startswith('['):
                        break
                    elif line.startswith(f'{variable} = '):
                        return line.split(' = ')[-1]
                    elif line.startswith(f'{variable}='):
                        return line.split('=')[-1]
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

    # See if the section is already there
    section_is_there = False
    for line in lines_lst:
        if '[{section}]'.format(section=section) in line:
            section_is_there = True
            break

    # Make list for new lines
    new_lines_lst = []

    # Make new lines to add
    section_line_to_add = '[{section}]'.format(section=section)
    variable_line_to_add = variable + ' = ' + value

    # If section was there, add a line after the section with new variable and value
    if section_is_there:
        for line in lines_lst:
            new_lines_lst.append(line)
            if section_line_to_add in line:
                new_lines_lst.append(variable_line_to_add)
    else:
        # Add the existing lines first
        new_lines_lst = lines_lst
        # At the end, add the new section
        new_lines_lst.append('\n' + section_line_to_add)
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
    variable_line_to_set = variable + ' ='

    in_good_section = False
    for line in lines_lst:
        line_appended_this_round = False
        if section_line in line:
            in_good_section = True
        if in_good_section:
            if f'{variable} = ' in line:
                new_lines_lst.append(f'{variable} = {value}')
                in_good_section = False
                line_appended_this_round = True
            elif f'{variable}=' in line:
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
    return_val = config_section_map(cfg_file_path, section, variable, bypass_error=True)
    print(f'Return Value: "{return_val}"')
    if return_val is None:
        print('Variable is None, adding variable...')
        config_add_variable(cfg_file_path, section, variable, value)
    else:
        print('Variable exists, setting variable...')
        config_set_variable(cfg_file_path, section, variable, value)

