from pathlib import Path
import commonUtils.fileUtils as fileUtils
from PIL import Image, ImageStat
from commonUtils.debugUtils import *
from typing import *


image_file_cls_supported_ext_lst = ['jpg', 'jpeg', 'bmp', 'tif', 'tiff', 'webp', 'png']  # Supported Extensions by the ImageFile class


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
            log(Severity.CRITICAL, "fileUtils.imageUtils.ImageFile.__set_width_height",
                f"Failed to read image dimensions for {self.path}: {e}")

    from PIL import Image, ImageChops

    def __set_color_property(self, chroma_std_threshold: float = 2.5, sample_max: int = 512) -> bool:
        """
        Sets and returns self.color:
          - True  => color image
          - False => grayscale image

        Heuristic:
          - Convert to YCbCr and examine stddev of Cb/Cr (chroma) channels.
          - Truly grayscale images have ~flat Cb/Cr => very low stddev.
          - JPEG artifacts or slight noise tolerated via threshold.

        Params:
          chroma_std_threshold: raise to be more forgiving (treat near-gray as grayscale).
          sample_max: downsize longest edge to this for speed; does not affect accuracy much.
        """
        try:
            with Image.open(self.path) as img:
                # Fast path for obvious grayscale modes
                if img.mode in ("1", "L", "LA"):
                    self.color = False
                    return self.color

                # Normalize to YCbCr
                ycbcr = img.convert("YCbCr")

                # Optional downscale for speed on huge images
                w, h = ycbcr.size
                m = max(w, h)
                if m > sample_max:
                    scale = sample_max / float(m)
                    ycbcr = ycbcr.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.BILINEAR)

                _, cb, cr = ycbcr.split()
                cb_std = ImageStat.Stat(cb).stddev[0]
                cr_std = ImageStat.Stat(cr).stddev[0]

                # If both chroma stddevs are tiny, it's grayscale
                is_color = (cb_std > chroma_std_threshold) or (cr_std > chroma_std_threshold)
                self.color = is_color
                return self.color

        except Exception as e:
            log(Severity.CRITICAL, "fileUtils.imageUtils.ImageFile.__set_color_property",
                f"Failed to determine if image is color for {self.path}: {e}")
            raise

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
                self.compressed_image.color = self.color

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


