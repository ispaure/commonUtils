import os
import stat
from shutil import rmtree
from pathlib import Path
import sys
import subprocess
from shutil import copyfile


class File:
    def __init__(self, path):
        self.path = path
        self.name = self.get_name()

    def get_name(self):
        name_incl_ext = self.path.split(get_split_character())[-1]
        if '.' in name_incl_ext:
            return name_incl_ext.split('.').join('.')[-1]
        else:
            return name_incl_ext

    def get_ext(self):
        if '.' in self.path.split(get_split_character())[-1]:
            pass


def get_file_path_list(dir_name, recursive=True, filter_extension=None):
    """
    Returns list of all files under a specific directory.
    :param dir_name: Directory in which to look under
    :type dir_name: str
    :param recursive: Indicate if sub-directories should be included, recursively
    :param filter_extension: File extension to retain (when just want to retain all .txt files for example)
    :type filter_extension: str
    :rtype: lst
    """
    # create a list of file and subdirectories
    # names in the given directory
    list_of_files = os.listdir(dir_name)
    all_files = list()
    # Iterate over all the entries
    for entry in list_of_files:
        # Create full path
        full_path = os.path.join(dir_name, entry)
        # If entry is a directory then get the list of files in this directory
        if os.path.isdir(full_path):
            if recursive:
                all_files = all_files + get_file_path_list(full_path)
        else:
            all_files.append(full_path)

    # If set a file type filter, filter.
    if filter_extension is not None:
        filtered_files = list()
        for file in all_files:
            if '.' + filter_extension.lower() == file[-len(filter_extension)-1:].lower():
                filtered_files.append(file)
        return filtered_files

    return all_files


def read_file(file_path):
    """
    Returns each line of a text file as part of a list.
    :param file_path: File path to read
    :type file_path: str
    :rtype: lst
    """
    f = open(file_path, 'r')
    return f.read().splitlines()


def append_line_lst_to_file(line_lst, file_path):
    """
    Appends a list of lines to the end of a file
    """
    for line in line_lst:
        with open(file_path, 'a') as f:
            f.write('\n' + line)


def get_dirs_path_list(dir_path):
    """
    Returns a list of valid directory paths within a directory. Function copied from Blue Hole Addon scripts.
    :param dir_path: Directory in which to look for directories
    :type dir_path: str
    :rtype: lst
    """
    dir_path_lst = []
    # Get list of items within a directory
    atlas_sub_dir_item_lst = os.listdir(dir_path)
    # Create a path from items within the directory, and if they are a directory, add them to the directories list.
    for item in atlas_sub_dir_item_lst:
        item_dir = str(Path(dir_path, item))
        if os.path.isdir(item_dir):
            dir_path_lst.append(item_dir)
    return dir_path_lst


def delete_dir(dir_path):
    """
    Deletes a directory on disk
    """
    rmtree(dir_path)


def delete_dir_contents(dir_path):
    """
    Deletes the files and folders within a directory (not the directory itself)
    """
    # Make sure everything is not marked as non-writable
    for root, dirs, files in os.walk(dir_path):
        for fname in files:
            full_path = os.path.join(root, fname)
            os.chmod(full_path, stat.S_IWRITE)

    # Wipe contents within dir
    rem_dir_lst = get_dirs_path_list(dir_path)
    for rem_dir in rem_dir_lst:
        delete_dir(rem_dir)
    rem_file_lst = get_file_path_list(dir_path)
    for rem_file in rem_file_lst:
        delete_file(rem_file)


def delete_file(file_path):
    os.remove(file_path)


def delete_symbolic_link(dir_path):
    try:
        os.unlink(dir_path)
    except:
        try:
            os.remove(dir_path)
        except:
            pass


def create_symbolic_link(source_dir, destination_dir):
    """
    Creates a symbolic link from the source dir to the destination dir
    """
    os.symlink(source_dir, destination_dir)


def get_split_character():
    if sys.platform == 'win32':
        split_character = '\\'
    else:
        split_character = '/'
    return split_character


def open_dir_path(dir_path):
    """
    Opens the directory path that is given as a string
    :param dir_path: Directory to open
    :type dir_path: str
    """
    if os.path.isdir(dir_path):  # Validate string is in fact a path
        if sys.platform == "win32":
            os.startfile(dir_path)
        else:
            opener = "open" if sys.platform == "darwin" else "xdg-open"
            subprocess.call([opener, dir_path])
    else:
        print('ERROR: UNABLE TO OPEN PROJECT DIRECTORY.'
              '\nAttempted path: ' + dir_path)


def write_file(file_path, write_str):
    """
    Creates a file (if not created yet) and writes to it
    :param file_path: Path to write to
    :type file_path: str
    :param write_str: String to write
    :type write_str: str
    """
    # Get folder in which the file is
    file_dir = Path(file_path).parent

    # Create directory to store file in, if not created yet
    Path(file_dir).mkdir(parents=True, exist_ok=True)

    # Write to the file
    f = open(file_path, 'w+')
    f.write(write_str)
    f.close()

    # If macOS, ensure can be run
    if not sys.platform == 'win32':
        subprocess.check_call(['chmod', '+x', file_path])


def search_replace_xml(xml_file_path, search_str, replace_str):
    """
    Search and replace in designated xml file. Overwrites file with results.
    :param xml_file_path: Path of XML file (must incl. ext.)
    :type xml_file_path: str
    :param search_str: String to search for
    :type search_str: str
    :param replace_str: String to replace with
    :type replace_str: str
    """

    new_line_lst = []
    reading_file = open(xml_file_path, "r")
    content = reading_file.read()
    for line in content.splitlines():  # or whatever arbitrary loop
        line_decoded = line
        line_replaced = line_decoded.replace(search_str, replace_str)
        new_line_lst.append(line_replaced)

    print('THIS FILE HAS LINES: ' + str(len(new_line_lst)))
    reading_file = open(xml_file_path, 'w')

    current_line_count = 0
    for line in new_line_lst:
        current_line_count += 1

        if current_line_count < len(new_line_lst):
            reading_file.write(line + '\n')
        else:
            reading_file.write(line)

    reading_file.close()


def write_file_append(file_path, write_str):
    """
    Appends text on an additional line in an existing text file
    """
    with open(file_path, 'a') as f:
        f.write('\n' + str(write_str))


def rename_file(original_name, new_name, force=False):
    """
    Renames a file on disk
    """

    # If force set to On, Windows + File Path exists already, delete it before renaming file
    if sys.platform == 'win32' and force and os.path.exists(new_name):
        delete_file(new_name)

    os.rename(original_name, new_name)


def copy_file(source, destination):
    """
    Copies file from source to destination.
    """
    # If destination directory does not exist, create
    destination_dir = os.path.dirname(destination)
    make_dir(destination_dir)

    # Copy file
    copyfile(source, destination)


def make_dir(directory):
    """
    Creates directory at location (if it doesn't exist)
    """
    if not os.path.exists(directory):
        Path(directory).mkdir(parents=True, exist_ok=True)


def get_current_working_dir() -> Path:
    cwd = Path(os.getcwd())
    if cwd.name == 'Python':
        return cwd
    else:
        return Path(cwd, 'Python')
