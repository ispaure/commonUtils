from typing import *
from pathlib import Path
import os
import sys
import shutil
import subprocess
from shutil import make_archive

# Compression utilities
import pyzipper
import patoolib
import zipfile

# Common utilities
from commonUtils import fileUtils
from commonUtils.osUtils import *
from commonUtils.debugUtils import *


def unzip_file(source_file: Union[str, Path], destination_dir: Union[str, Path], pwd: bool = None):
    """
    Extracts zip file to desired location.
    :param source_file: Path to file to extract.
    :type source_file: str
    :param destination_dir: Directory to extract into.
    :type destination_dir: str
    :param pwd: Password for extraction. Leave none if archive is not password protected.
    :type pwd: str
    """
    tool_name = 'Extract ZIP File'

    if isinstance(source_file, Path):
        source_file_str = str(source_file)
    elif isinstance(source_file, str):
        source_file_str = source_file
    else:
        log(Severity.ERROR, tool_name, 'Wrong Input type for Source File')
        return

    if isinstance(destination_dir, Path):
        destination_dir_str = str(destination_dir)
    elif isinstance(destination_dir, str):
        destination_dir_str = destination_dir
    else:
        log(Severity.ERROR, tool_name, 'Wrong Input type for Destination Directory')
        return

    if pwd is None:
        log(Severity.DEBUG, tool_name, f'Extracting archive from "{source_file}" to "{destination_dir}"')
        with zipfile.ZipFile(source_file_str, 'r') as zip_ref:
            zip_ref.extractall(destination_dir_str)
    else:
        log(Severity.DEBUG, tool_name, f'Extracting password-protected archive from "{source_file}" to "{destination_dir}"')
        # # Legacy: Only works with ZIP 2.0 encryption method (legacy; unsecure)
        # with zipfile.ZipFile(source_file, 'r') as zip_ref:
        #     zip_ref.extractall(path=destination_dir, members=None, pwd=pwd.encode())

        # Following method works with both ZIP 2.0 AND AES-256 encryption methods (secure)
        with pyzipper.AESZipFile(source_file_str, 'r', compression=pyzipper.ZIP_DEFLATED,
                                 encryption=pyzipper.WZ_AES) as extracted_zip:
            extracted_zip.extractall(path=destination_dir_str,
                                     pwd=str.encode(pwd))


def unrar_file(source_file, destination_dir, unrar_sw_path: str = None):
    """
    Extracts rar file to desired location.
    :param source_file: Path to file to extract.
    :type source_file: str
    :param destination_dir: Directory to extract into.
    :type destination_dir: str
    :param unrar_sw_path: Path to the unrar software (for macOS)
    :type unrar_sw_path: str
    """
    tool_name = 'Extract RAR File'
    if sys.platform == 'win32':
        log(Severity.DEBUG, Severity.DEBUG, f'Extracting archive from "{source_file}" to "{destination_dir}"')
        patoolib.extract_archive(source_file, outdir=destination_dir)
    else:
        log(Severity.DEBUG, Severity.DEBUG, f'Extracting archive from "{source_file}" to "{destination_dir}"')
        patoolib.extract_archive(source_file, outdir=destination_dir, program=unrar_sw_path)
    # TODO: Doesn't work for macos because cant find software. Need program= flag with proper software
    # TODO: Or alternate solution is interfacing with Keka through Commandline perhaps?: https://github.com/aonez/Keka/wiki/Terminal-support


def zip_file(source, destination, keep_root=True):
    """
    Create a zip file from the source to the destination.
    :param source: Source path to compress
    :type source: str
    :param destination: Destination path of compressed archive (incl. extension)
    :type destination: str
    :param keep_root: When source is a dir, keeps the dir as part of the archive as a root folder (Default true)
    :type keep_root: bool
    """
    def make_zipfile_keep_root(output_filename, source_dir):
        relroot = os.path.abspath(os.path.join(source_dir, os.pardir))
        with zipfile.ZipFile(output_filename, "w", zipfile.ZIP_DEFLATED) as zip:
            for root, dirs, files in os.walk(source_dir):
                # add directory (needed for empty dirs)
                zip.write(root, os.path.relpath(root, relroot))
                for file in files:
                    filename = os.path.join(root, file)
                    if os.path.isfile(filename):  # regular files only
                        arcname = os.path.join(os.path.relpath(root, relroot), file)
                        zip.write(filename, arcname)

    def make_zipfile_discard_root(source, destination):
        make_archive(destination, 'zip', source)

    if keep_root:
        make_zipfile_keep_root(destination, source)
    else:
        make_zipfile_discard_root(source, destination[:-len('.zip')])


def extract_file_from_dmg(dmg_path, target_filename, output_dir):
    tool_name = 'DMG File Extractor'
    # Make sure on macOS
    if get_os() != OS.MAC:
        log(Severity.ERROR, tool_name, 'OS Unsupported for this operation!')
        return

    # Step 1: Mount the DMG
    try:
        log(Severity.DEBUG, tool_name, f'Mounting DMG File "{dmg_path}"')
        mount_output = subprocess.check_output(["hdiutil", "attach", dmg_path], text=True)
    except subprocess.CalledProcessError as e:
        log(Severity.ERROR, tool_name, f"Failed to mount DMG: {e}")
        return

    # Parse the mount point from the output
    lines = mount_output.splitlines()
    mount_point = None
    for line in lines:
        if "/Volumes/" in line:
            mount_point = line.split("\t")[-1]
            break

    if not mount_point:
        log(Severity.ERROR, tool_name, f"Failed to find the mount point: '{dmg_path}'")
        return

    try:
        # Step 2: Find the target file
        target_path = os.path.join(mount_point, target_filename)
        if not os.path.exists(target_path):
            log(Severity.ERROR, tool_name, f"{target_filename} not found in the DMG.")
            return

        # Step 3: Copy the file to the output directory
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        shutil.copy(target_path, output_dir)
        log(Severity.DEBUG, tool_name, f"Copied {target_filename} to {output_dir}")

    finally:
        # Step 4: Unmount the DMG
        subprocess.call(["hdiutil", "detach", mount_point])


def extract_directory_from_dmg(dmg_path, target_directory, output_dir):
    tool_name = 'DMG Directory Extractor'
    # Make sure on macOS
    if get_os() != OS.MAC:
        log(Severity.ERROR, tool_name, 'OS Unsupported for this operation!')
        return

    # Step 1: Mount the DMG
    try:
        log(Severity.DEBUG, tool_name, f'Mounting DMG File "{dmg_path}"')
        mount_output = subprocess.check_output(["hdiutil", "attach", dmg_path], text=True)
    except subprocess.CalledProcessError as e:
        log(Severity.ERROR, tool_name, f"Failed to mount DMG: {e}")
        return

    # Parse the mount point from the output
    lines = mount_output.splitlines()
    mount_point = None
    for line in lines:
        if "/Volumes/" in line:
            mount_point = line.split("\t")[-1]
            break

    if not mount_point:
        log(Severity.ERROR, tool_name, f"Failed to find the mount point: '{dmg_path}'")
        return

    try:
        # Step 2: Find the target directory
        target_path = os.path.join(mount_point, target_directory)
        if not os.path.isdir(target_path):
            log(Severity.ERROR, tool_name, f"{target_directory} not found in the DMG.")
            return

        # Step 3: Copy the directory to the output location
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        destination = os.path.join(output_dir, os.path.basename(target_directory))
        shutil.copytree(target_path, destination)
        log(Severity.DEBUG, tool_name, f"Copied {target_directory} to {output_dir}")

    finally:
        # Step 4: Unmount the DMG
        subprocess.call(["hdiutil", "detach", mount_point])
