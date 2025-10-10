from pathlib import Path
import commonUtils.fileUtils as fileUtils
from PIL import Image
from commonUtils.debugUtils import *
from typing import *


image_file_cls_supported_ext_lst = ['jpg', 'jpeg', 'bmp', 'tiff', 'webp', 'png']  # Supported Extensions by the ImageFile class


class ImageFile(fileUtils.File):
    def __init__(self, path: Path):
        super().__init__(path)

        # Image-specific properties
        self.width: int = 0
        self.height: int = 0
        self.__set_width_height()
        self.color: Union[bool, None] = None

        self.compressed_image: Union[ImageFile, None] = None  # Gets updated with an ImageFile class if image gets compressed

    def __set_width_height(self):
        """Safely reads image dimensions without fully decoding the image."""
        try:
            with Image.open(self.path) as img:
                self.width, self.height = img.size
        except Exception as e:
            log(Severity.CRITICAL, "fileUtils.imageUtils.ImageFile._load_dimensions",
                f"Failed to read image dimensions for {self.path}: {e}")

    def __set_color_property(self):
        """
        Returns True if the image is in color, False if it's grayscale.
        Efficiently checks image mode or pixel variance.
        """
        try:
            with Image.open(self.path) as img:
                # Fast-path: mode already indicates grayscale
                if img.mode in ("1", "L", "LA"):
                    return False
                if img.mode in ("RGB", "RGBA", "P"):
                    # Convert to RGB to normalize channels
                    rgb_img = img.convert("RGB")

                    # Get a small sample (10x10 or entire if smaller)
                    w, h = rgb_img.size
                    sample = rgb_img.crop((0, 0, min(10, w), min(10, h)))

                    # Get pixel data
                    pixels = list(sample.getdata())

                    # If all pixels have R=G=B → grayscale
                    for r, g, b in pixels:
                        if r != g or g != b:
                            return True
                    self.color = False

                # Other modes (CMYK, etc.) are assumed color
                self.color = True

        except Exception as e:
            log(Severity.WARNING, "fileUtils.imageUtils.ImageFile.__is_color",
                f"Failed to determine if image is color for {self.path}: {e}")
            return True  # assume color if uncertain

    def compress_to_jpg(self, dest_path, quality_grayscale: int, quality_color: int):
        """
        Compresses the image file to a .JPG at the destination path.

        - Automatically converts non-RGB formats (e.g. RGBA, P) to RGB.
        - Overwrites existing file at dest_path if present.
        - 'quality' ranges from 1 (lowest) to 95 (highest). Default = 90.
        """

        try:
            with Image.open(self.path) as img:

                # Set color property (if it is not loaded yet)
                if self.color is None:
                    self.__set_color_property()

                # If grayscale, use grayscale quality, else use color quality
                if self.color:
                    quality = quality_color
                else:
                    quality = quality_grayscale

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

    def get_description(self):
        if self.color is None:
            color_description = 'Undefined'
        elif self.color:
            color_description = 'Color'
        else:
            color_description = 'Grayscale'
        return (f'{self.name}.{self.ext} - Dimensions: {self.width}x{self.height}, Color: {color_description}, '
                f'Size {self.size} bytes')


