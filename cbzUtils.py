"""
Hosts functions related to CBZ (ComicBook Zip) files
"""
from __future__ import annotations
from pathlib import Path
from typing import *
import commonUtils.fileUtils as fileUtils
import commonUtils.xmlUtils as xmlUtils
import commonUtils.zipUtils as zipUtils
import commonUtils.imageUtils as imageUtils
from commonUtils.debugUtils import *
from datetime import datetime


# User Defined Settings

# Default directory for conversion (What shows up as default in the UI)
default_path_to_convert = Path(fileUtils.get_user_home_dir(), 'ComicsTest', 'ToConvert')

# Compression 'quality' ranges from 1 (lowest, smallest size) to 95 (highest, biggest size)
jpg_quality_color = 40  # Should be higher for color than grayscale, else causes much-worse looking results
jpg_quality_grayscale = 10  # Can be much lower than color, still yielding great results

# Decide to keep the compressed image if its size is smaller than this percentage of the original.
minimum_allowed_compression_percentage = 75

# Temporary Folders for Compression
temp_compression_path = Path(fileUtils.get_user_home_dir(), 'Temp_CBZ_Compression')
temp_dir_extracted_cbz = Path(temp_compression_path, '1_Extracted_CBZ')
temp_dir_compressed_jpgs = Path(temp_compression_path, '2_Compressed_JPGs')
temp_dir_result = Path(temp_compression_path, '3_Result')


tool_name = 'commonUtils.cbzUtils'
batch_target_dir: Union[str, None] = None  # Updated in code to the batch target dir


class ComicInfoXML(xmlUtils.XMLFile):
    def __init__(self, path: Path):
        super().__init__(path)

    def update_pages_in_line_lst(self, cbz_image_file_lst: List[CBZImageFile]):

        # Check line list is not currently empty
        if len(self.line_lst) == 0:
            log(Severity.CRITICAL, tool_name, 'Cannot Update Pages in ComicInfo.xml line List as it is empty and not loaded!')

        # Passed through pages section correctly
        went_through_pages_section = False

        # Build up the list of lines
        updated_line_lst = []
        in_page_section = False
        for line in self.line_lst:
            if not in_page_section:
                updated_line_lst.append(line)
                if line == '  <Pages>':
                    in_page_section = True
                    page_number = 0
                    for cbz_image_file in cbz_image_file_lst:
                        page_line = cbz_image_file.get_comicinfo_xml_line(page_number)
                        updated_line_lst.append(page_line)
                        page_number += 1
            else:
                if line == '  </Pages>':
                    updated_line_lst.append(line)
                    in_page_section = False
                    went_through_pages_section = True

        if not went_through_pages_section:
            log(Severity.CRITICAL, tool_name, f'Did not go through Pages Section of ComicInfo.XML! {self.line_lst}')

        self.line_lst = updated_line_lst


class CompressionStats:
    def __init__(self):
        self.has_comicinfo_xml: Optional[bool] = None
        self.original_images_size = 0
        self.compressed_images_size = 0
        self.kept_images_size = 0
        self.kept_images_compressed_cnt = 0
        self.kept_images_original_cnt = 0

    def reset(self):
        for key in (
            "original_images_size", "compressed_images_size",
            "kept_images_size", "kept_images_compressed_cnt",
            "kept_images_original_cnt"
        ):
            setattr(self, key, 0)
        self.has_comicinfo_xml = None

    def __add__(self, other: CompressionStats) -> CompressionStats:
        new = CompressionStats()
        for key in (
            "original_images_size", "compressed_images_size",
            "kept_images_size", "kept_images_compressed_cnt",
            "kept_images_original_cnt"
        ):
            setattr(new, key, getattr(self, key) + getattr(other, key))
        return new

    def __iadd__(self, other: CompressionStats) -> CompressionStats:
        for key in (
            "original_images_size", "compressed_images_size",
            "kept_images_size", "kept_images_compressed_cnt",
            "kept_images_original_cnt"
        ):
            setattr(self, key, getattr(self, key) + getattr(other, key))
        return self

    def get_summary(self):
        summary = ("Compression Statistics:\n"
                   f"  |Images|\n"
                   f"    Original # Kept:     {self.kept_images_original_cnt}"
                   f"    Compressed # Kept:   {self.kept_images_compressed_cnt}\n"
                   f"  |Archive|\n"
                   f"    Original Size:       {self.original_images_size} bytes\n"
                   f"    New Size:            {self.kept_images_size} bytes\n"
                   f"    Savings (%):         {self.kept_images_size/self.original_images_size*100}%")
        return summary

    def print_summary(self):
        """Print only the integer stats in a clean format."""
        print(self.get_summary())


class CompressionLog:
    def __init__(self, name: str):
        self.name: str = name
        self.ext = 'cbz'
        self.__compression_log_line_lst: List[str] = []

    def append(self, string: str):
        self.__compression_log_line_lst.append(f'{string}\n')

    def append_skip_line(self):
        self.__compression_log_line_lst.append('')

    def reset(self):
        self.__compression_log_line_lst = []

    def export(self, export_path: Path):
        fileUtils.write_file(export_path, self.__compression_log_line_lst)


class CBZImageFile(imageUtils.ImageFile):
    def __init__(self, path: Path):
        super().__init__(path)
    
    def get_comicinfo_xml_line(self, page_num: int):
        """
        Get the line for the image as it would appear in ComicInfo.XML
        """
        if page_num == 0:
            return f'    <Page Image="{page_num}" ImageSize="{self.size}" ImageWidth="{self.width}" ImageHeight="{self.height}" Type="FrontCover" />'
        else:
            return f'    <Page Image="{page_num}" ImageSize="{self.size}" ImageWidth="{self.width}" ImageHeight="{self.height}" />'


class CBZFile(zipUtils.ZIPFile):
    # TODO: Add function to rename image files if 1.jpg etc. because ComicRack doesn't read these properly. Add padding to them if that happens and repack. Before doing compression, in a separate function entirely.
    # TODO: Test with a large comics folder and see if issues occur.
    # TODO: Detect if image is black and white vs. color and apply different compression settings (BW is more forgiving)
    def __init__(self, path: Path):
        super().__init__(path)

        # Check if correct extension
        self.is_valid = self.ext == 'cbz'
        if not self.is_valid:
            log(Severity.CRITICAL, tool_name, f'This CBZFile is invalid: {self.path}')

        # Compression stats
        self.compression_stats: CompressionStats = CompressionStats()
        # Compression log
        self.compression_log: CompressionLog = CompressionLog(self.name)
        self.__compression_log_line_lst: List[str] = []

    def is_already_compressed(self):
        return any(f == 'CompressionLog.txt' for f in self.get_root_file_lst())

    def compress_to_jpgs(self):
        func_name = 'compress_to_jpgs'

        # Reset Stats and Log
        self.compression_stats.reset()
        self.compression_log.reset()

        self.compression_log.append(f'Compression Log for {self.name}.{self.ext}')
        self.compression_log.append(f'Time: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
        self.compression_log.append_skip_line()

        # Simplify Path for Logging (if possible)
        if batch_target_dir is not None:
            path_str = str(self.path)
            simplified_path = path_str.replace(batch_target_dir, '...')
        else:
            simplified_path = str(self.path)
        # Log Compressing
        log(Severity.INFO, tool_name, f'Compressing "{simplified_path}"!')

        # Create Extracted_CBZ Directory
        fileUtils.create_n_wipe_dir(temp_dir_extracted_cbz)

        # Extract .CBZ in Directory
        self.extract(temp_dir_extracted_cbz)

        # If there is any subdirectory, it's unexpected. Critical error
        if fileUtils.has_subdirectories(temp_dir_extracted_cbz):
            log(Severity.CRITICAL, f'cbzUtils.CBZFile.{func_name}', f'Unexpected Directory within {self.path}')

        # Attempt to find ComicInfo.xml
        comic_info_xml_path = Path(temp_dir_extracted_cbz, 'ComicInfo.xml')
        if os.path.isfile(comic_info_xml_path):
            comic_info_xml = ComicInfoXML(comic_info_xml_path)
            self.compression_stats.has_comicinfo_xml = True
        else:
            comic_info_xml = None
            self.compression_stats.has_comicinfo_xml = False

        # Gather images as class list
        img_file_cls_lst: List[CBZImageFile] = []
        extracted_file_path_lst = fileUtils.get_file_path_list(temp_dir_extracted_cbz, recursive=False)
        for extracted_file_path in extracted_file_path_lst:
            file_path = Path(extracted_file_path)
            file_cls = fileUtils.File(file_path)
            if file_cls.ext in imageUtils.image_file_cls_supported_ext_lst:
                image_file_cls = CBZImageFile(file_path)
                self.compression_stats.original_images_size += image_file_cls.size
                img_file_cls_lst.append(image_file_cls)
            elif str(file_cls.path) != str(comic_info_xml_path):
                log(Severity.CRITICAL, f'cbzUtils.CBZFile.{func_name}', f'Unexpected File within "{self.path}": "{file_cls.path}"')

        # Create Compressed_JPGs Directory
        fileUtils.create_n_wipe_dir(temp_dir_compressed_jpgs)

        # Convert to JPG
        for img_file_cls in img_file_cls_lst:
            img_file_cls.compress_to_jpg(dest_path=Path(temp_dir_compressed_jpgs, f'{img_file_cls.name}.jpg'), quality=jpg_quality)
            self.compression_stats.compressed_images_size += img_file_cls.compressed_image.size

        # Create Result Directory
        fileUtils.create_n_wipe_dir(temp_dir_result)

        # Select compressed image if at least smaller by specified amount, else keep original
        page_count = 0
        kept_image_cls_lst: List[CBZImageFile] = []
        for img_file_cls in img_file_cls_lst:
            page_count += 1
            if img_file_cls.compressed_image.size < img_file_cls.size * minimum_allowed_compression_percentage / 100:
                kept_image_cls = img_file_cls.compressed_image
                self.compression_log.append(f'Page #{page_count:04d}: "{kept_image_cls.get_description}, Verdict: Compressed Image')
                self.compression_stats.kept_images_compressed_cnt += 1
            else:
                kept_image_cls = img_file_cls
                self.compression_log.append(f'Page #{page_count:04d}: {kept_image_cls.get_description}, Verdict: Original Image')
                self.compression_stats.kept_images_original_cnt += 1
            self.compression_stats.kept_images_size += kept_image_cls.size
            kept_image_cls_lst.append(kept_image_cls)

        # Move kept images to result folder
        for kept_image_cls in kept_image_cls_lst:
            fileUtils.copy_file(kept_image_cls.path, Path(temp_dir_result, f'{kept_image_cls.name}.{kept_image_cls.ext}'))

        # Rebuild ComicInfo.XML
        if comic_info_xml is not None:
            comic_info_xml.import_line_lst()
            comic_info_xml.update_pages_in_line_lst(kept_image_cls_lst)
            comic_info_xml.export(Path(temp_dir_result, 'ComicInfo.xml'))

        # Add summary to compression log
        self.compression_log.append_skip_line()
        self.compression_log.append(self.compression_stats.get_summary())
        # Dump Compression Log File on Disk
        self.compression_log.export(Path(temp_dir_result, 'CompressionLog.txt'))

        # Overwrite existing .CBZ with contents of the Result Directory
        zipUtils.zip_file(temp_dir_result, self.path, keep_root=False)

        # fileUtils.hang_n_terminate()
        # Wipe directories
        fileUtils.delete_dir_contents(temp_compression_path)

        # Log Finished Compression
        log(Severity.INFO, tool_name, f'Completed Compression of "{simplified_path}"!')


def batch_compress_cbz(target_dir: Union[str, Path], recursive: bool = True):
    """
    Tool to compress .CBZ files, so they take less space. Only tested on macOS for now.

    1. Builds up a list of all .CBZ files in a given directory (recursively)
    2. For each .CBZ file which does not contain a CompressionLog.txt file:
        a.) Wipe ~/Temp_CBZ_Compression (recursively). Confirm it worked.
        b.) Extract .CBZ in ~/Temp_CBZ_Compression/Extracted_CBZ
        c.) Get list of extracted image files (.BMP, .JPG, .JPEG, .PNG, .WEBM) <- Throw error if sub-folders or unexpected file types
        d.) Compress as .JPG format (using desired compression setting) in ~/Temp_CBZ_Compression/Compressed_JPGs
        For each compressed .JPG file:
            a.) If at least 25% smaller than the original, copy compressed (else, original) to ~/Temp_CBZ_Compression/Result
        e.) If ComicInfo.XML file in ~Temp_CBZ_Compression/Input, recreate using resulting images in Output dir
        f.) Write a CompressionLog.txt file in Output, logging if originals or compressed version is kept
        g.) Compress contents of ~/Temp_CBZ_Compression/Output to .CBZ, overwriting the original file
    3. Write to console that conversion is complete, giving a brief summary outlining the following:
        -Compressed Number of .CBZ Files / Total Number of .CBZ Files (Newly Compressed vs Already Compressed)
        -Amount of Images Compressed that were kept vs using original instead (Number & Percentage)
        -Space Savings (Before -> After) (Number & Percentage)
    :param target_dir:
    :param recursive: When True, compress .CBZ within subdirectories
    """
    global batch_target_dir
    batch_target_dir = str(target_dir)
    # Display basic information in console
    log_message = f'Initialize Batch Compress .CBZ in {target_dir} '
    if recursive:
        log_message += '(Recursive)'
    else:
        log_message += '(Not Recursive)'
    log(Severity.INFO, tool_name, log_message)

    # Get list of .CBZ Files (as strings)
    cbz_file_path_lst: List[str] = fileUtils.get_file_path_list(target_dir, recursive, filter_extension='cbz')

    # Build list of CBZFile
    cbz_file_cls_lst: List[CBZFile] = []
    for cbz_file_path in cbz_file_path_lst:
        cbz_file_cls = CBZFile(Path(cbz_file_path))
        cbz_file_cls_lst.append(cbz_file_cls)

    # Filter for cbz files which need conversion
    cbz_file_cls_to_compress_lst: List[CBZFile] = []
    for cbz_file_cls in cbz_file_cls_lst:
        if not cbz_file_cls.is_already_compressed():
            cbz_file_cls_to_compress_lst.append(cbz_file_cls)

    # Log number of files not yet compressed
    log(Severity.INFO, tool_name, f'{len(cbz_file_cls_to_compress_lst)}/{len(cbz_file_cls_lst)} ({len(cbz_file_cls_to_compress_lst)/len(cbz_file_cls_lst)*100}%) of CBZ Files Awaiting Compression!')

    # Compress CBZ
    compression_stats = CompressionStats()
    for cbz_file in cbz_file_cls_to_compress_lst:
        cbz_file.compress_to_jpgs()
        compression_stats += cbz_file.compression_stats
    compression_stats.print_summary()


