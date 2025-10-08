"""
Hosts functions related to CBZ (ComicBook Zip) files
"""
from pathlib import Path
from typing import *
import commonUtils.fileUtils as fileUtils
import commonUtils.xmlUtils as xmlUtils
import commonUtils.zipUtils as zipUtils
import commonUtils.imageUtils as imageUtils
from commonUtils.debugUtils import *
from datetime import datetime


# User defined settings
default_path_to_convert = Path(fileUtils.get_user_home_dir(), 'ComicsTest', 'ToConvert')
jpg_quality = 40  # 'quality' ranges from 1 (lowest) to 95 (highest)
compression_tolerance = 75  # Keep the compressed image if it's no more than X % of the original. Else, keep original. (Only save space if compression was worth it)

# Temporary Folders for Compression
temp_compression_path = Path(fileUtils.get_user_home_dir(), 'Temp_CBZ_Compression')
temp_dir_extracted_cbz = Path(temp_compression_path, '1_Extracted_CBZ')
temp_dir_compressed_jpgs = Path(temp_compression_path, '2_Compressed_JPGs')
temp_dir_result = Path(temp_compression_path, '3_Result')


tool_name = 'commonUtils.cbzUtils'
batch_target_dir: Union[str, None] = None  # Updated in code to the batch target dir


class ComicInfoXML(fileUtils.File):
    def __init__(self, path: Path):
        super().__init__(path)


class CompressionStats:
    def __init__(self):
        self.start_datetime: str = ''
        self.has_comicinfo_xml: Union[bool, None] = None
        self.original_images_size: int = 0
        self.compressed_images_size: int = 0
        self.kept_images_size: int = 0
        self.kept_images_compressed_cnt: int = 0
        self.kept_images_original_cnt: int = 0

    def reset(self):
        self.start_datetime = ''
        self.has_comicinfo_xml = None
        self.original_images_size = 0
        self.compressed_images_size = 0
        self.kept_images_size = 0
        self.kept_images_compressed_cnt = 0
        self.kept_images_original_cnt = 0

    def __add__(self, other: "CompressionStats") -> "CompressionStats":
        new = CompressionStats()
        new.original_images_size = self.original_images_size + other.original_images_size
        new.compressed_images_size = self.compressed_images_size + other.compressed_images_size
        new.kept_images_size = self.kept_images_size + other.kept_images_size
        new.kept_images_compressed_cnt = self.kept_images_compressed_cnt + other.kept_images_compressed_cnt
        new.kept_images_original_cnt = self.kept_images_original_cnt + other.kept_images_original_cnt
        return new

    def __iadd__(self, other: "CompressionStats") -> "CompressionStats":
        self.original_images_size += other.original_images_size
        self.compressed_images_size += other.compressed_images_size
        self.kept_images_size += other.kept_images_size
        self.kept_images_compressed_cnt += other.kept_images_compressed_cnt
        self.kept_images_original_cnt += other.kept_images_original_cnt
        return self

    def print_summary(self):
        """Print only the integer stats in a clean format."""
        print("📊 Compression Statistics:")
        print(f"  Original images size:     {self.original_images_size}")
        print(f"  Compressed images size:   {self.compressed_images_size}")
        print(f"  Kept images total size:   {self.kept_images_size}")
        print(f"  Kept compressed count:    {self.kept_images_compressed_cnt}")
        print(f"  Kept original count:      {self.kept_images_original_cnt}")


class CBZImageFile(imageUtils.ImageFile):
    def __init__(self, path: Path):
        super().__init__(path)
        self.page_number: Union[int, None] = self.__get_page_number()
    
    def __get_page_number(self):
        for char in self.name:
            if char not in '0123456789':
                # TODO: Solve this
                # log(Severity.ERROR, 'cbzUtils.CBZImageFile', f'Cannot determine page number for {self.name}; non-numeric character in file name!')
                return None
        return int(self.name)


class CBZFile(zipUtils.ZIPFile):
    # TODO: Add function to rename image files if 1.jpg etc. because ComicRack doesn't read these properly. Add padding to them if that happens and repack. Before doing compression, in a separate function entirely.
    # TODO: Rebuild ComicInfo.xml file (update with newer resolution and/or size, so it doesn't crash ComicRack on opening the files)
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
        self.__compression_log_line_lst: List[str] = []

    def is_already_compressed(self):
        return any(f == 'CompressionLog.txt' for f in self.get_root_file_lst())

    def compress_to_jpgs(self):
        func_name = 'compress_to_jpgs'

        # Reset Log and Stats
        self.compression_stats.reset()
        self.reset_compression_log()

        self.append_to_compression_log(f'Compression Log for {self.name}.{self.ext}')
        self.compression_stats.start_datetime = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.append_to_compression_log(f'Start Date/Time: {self.compression_stats.start_datetime}')

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
            comic_info_xml = xmlUtils.XMLFile(comic_info_xml_path)
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
        self.append_to_compression_log(f'Original Images Size: {self.compression_stats.original_images_size} bytes')

        # Create Compressed_JPGs Directory
        fileUtils.create_n_wipe_dir(temp_dir_compressed_jpgs)

        # Convert to JPG
        for img_file_cls in img_file_cls_lst:
            img_file_cls.compress_to_jpg(dest_path=Path(temp_dir_compressed_jpgs, f'{img_file_cls.name}.jpg'), quality=jpg_quality)
            self.compression_stats.compressed_images_size += img_file_cls.compressed_image.size
        self.append_to_compression_log(f'Compressed Images Size: {self.compression_stats.compressed_images_size} bytes')

        # Create Result Directory
        fileUtils.create_n_wipe_dir(temp_dir_result)

        # Select compressed image if at least smaller by specified amount, else keep original
        kept_image_cls_lst: List[CBZImageFile] = []
        for img_file_cls in img_file_cls_lst:
            if img_file_cls.compressed_image.size < img_file_cls.size * compression_tolerance / 100:
                kept_image_cls = img_file_cls.compressed_image
                self.compression_stats.kept_images_compressed_cnt += 1
            else:
                kept_image_cls = img_file_cls
                self.compression_stats.kept_images_original_cnt += 1
            self.compression_stats.kept_images_size += kept_image_cls.size
            kept_image_cls_lst.append(kept_image_cls)

        # Add some statistics to the log file
        self.append_to_compression_log(f'Kept Images Size: {self.compression_stats.kept_images_size} bytes')
        self.append_to_compression_log(f'Kept Original Images Count: {self.compression_stats.kept_images_original_cnt} Image(s)')
        self.append_to_compression_log(f'Kept Compressed Images Count: {self.compression_stats.kept_images_compressed_cnt} Image(s)')

        # Move kept images to result folder
        for kept_image_cls in kept_image_cls_lst:
            fileUtils.copy_file(kept_image_cls.path, Path(temp_dir_result, f'{kept_image_cls.name}.{kept_image_cls.ext}'))

        # Dump Compression Log File on Disk
        self.export_compression_log(Path(temp_dir_result, 'CompressionLog.txt'))

        # Overwrite existing .CBZ with contents of the Result Directory
        zipUtils.zip_file(temp_dir_result, self.path, keep_root=False)

        # fileUtils.hang_n_terminate()
        # Wipe directories
        fileUtils.delete_dir_contents(temp_compression_path)

        # Log Finished Compression
        log(Severity.INFO, tool_name, f'Completed Compression of "{simplified_path}"!')

    def append_to_compression_log(self, string: str):
        self.__compression_log_line_lst.append(f'{string}\n')

    def reset_compression_log(self):
        self.__compression_log_line_lst = []

    def export_compression_log(self, export_path: Path):
        fileUtils.write_file(export_path, self.__compression_log_line_lst)


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


