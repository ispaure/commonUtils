from pathlib import Path
import commonUtils.fileUtils as fileUtils
from PIL import Image
from commonUtils.debugUtils import *
from typing import *


image_file_cls_supported_ext_lst = ['jpg', 'jpeg', 'bmp', 'tiff', 'webp', 'png']  # Supported Extensions by the ImageFile class


class ImageFile(fileUtils.File):
    def __init__(self, path: Path):
        super().__init__(path)
        self.compressed_image: Union[ImageFile, None] = None  # Gets updated with an ImageFile class if image gets compressed

    def compress_to_jpg(self, dest_path, quality):
        """
        Compresses the image file to a .JPG at the destination path.

        - Automatically converts non-RGB formats (e.g. RGBA, P) to RGB.
        - Overwrites existing file at dest_path if present.
        - 'quality' ranges from 1 (lowest) to 95 (highest). Default = 90.
        """

        try:
            with Image.open(self.path) as img:
                # Convert if image has alpha channel or palette
                if img.mode in ("RGBA", "LA", "P"):
                    img = img.convert("RGB")

                # Ensure the destination directory exists
                dest_path = Path(dest_path)
                dest_path.parent.mkdir(parents=True, exist_ok=True)

                # Save as JPEG
                img.save(dest_path, "JPEG", quality=quality, optimize=True)

                # Return an image file for the result
                self.compressed_image = self.__class__(dest_path)

        except Exception as e:
            log(Severity.CRITICAL, 'fileUtils.imageUtils.ImageFile.compress_to_jpg', f'Failed to convert/compress image {self.path}: {e}')


