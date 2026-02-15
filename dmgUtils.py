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

from typing import *
from pathlib import Path
import shutil
import subprocess

# Common utilities
from . import fileUtils
from .osUtils import *
from .debugUtils import *


class DMGFile(fileUtils.File):
    def __init__(self, path: Path):
        # Call the parent (File) initializer
        super().__init__(path)

    def extract_directory_from_dmg(self, target_directory, output_dir):
        tool_name = 'DMG Directory Extractor'
        # Make sure on macOS
        if get_os() != OS.MAC:
            log(Severity.ERROR, tool_name, 'OS Unsupported for this operation!')
            return

        # Step 1: Mount the DMG
        try:
            log(Severity.DEBUG, tool_name, f'Mounting DMG File "{self.path}"')
            mount_output = subprocess.check_output(["hdiutil", "attach", self.path], text=True)
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
            log(Severity.ERROR, tool_name, f"Failed to find the mount point: '{self.path}'")
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
