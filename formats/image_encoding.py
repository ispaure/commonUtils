"""Optional Pillow image encoding; publication and retention policy are caller-owned."""

from typing import Callable
from pathlib import Path
from io import BytesIO
from PIL import Image, ImageOps, ImageCms, ImageStat


class UnsupportedImageFormat(ValueError):
    """The requested encoder is not supported."""


def _prepare_pixels(image, extension, preserve_alpha, icc_profile):
    """Convert the color profile with its pixels before choosing RGB or RGBA."""
    has_alpha = "A" in image.getbands() or "transparency" in image.info
    converts_to_rgb = extension == ".webp" or (
        extension in (".jpg", ".jpeg") and (has_alpha or image.mode == "P")
    )
    if icc_profile and converts_to_rgb:
        source_profile = ImageCms.ImageCmsProfile(BytesIO(icc_profile))
        color_space = source_profile.profile.xcolor_space.strip()
        if color_space != "RGB":
            # WebP and JPEG alpha/palette removal produce RGB pixels.
            # Convert non-RGB profiles with the pixels before encoding.
            alpha = image.convert("RGBA").getchannel("A") if has_alpha else None
            input_mode = {"CMYK": "CMYK", "GRAY": "L"}.get(color_space)
            if input_mode is None:
                raise ValueError(f"Unsupported ICC color space: {color_space}")
            output_profile = ImageCms.ImageCmsProfile(
                ImageCms.createProfile("sRGB")
            )
            image = ImageCms.profileToProfile(
                image.convert(input_mode),
                source_profile,
                output_profile,
                outputMode="RGB",
            )
            if alpha is not None:
                image.putalpha(alpha)
            icc_profile = output_profile.tobytes()
    if has_alpha and preserve_alpha and extension == ".webp":
        image = image.convert("RGBA")
    elif has_alpha or image.mode == "P":
        image = image.convert("RGB")
    return image, icc_profile


def _downscale(image, max_long_edge, max_height):
    """Apply the stricter positive bound, preserving aspect ratio and never upscaling."""
    width, height = image.size
    scale = 1.0
    if max_height is not None and max_height > 0 and height > max_height:
        scale = min(scale, max_height / float(height))
    if max_long_edge is not None and max_long_edge > 0 and max(width, height) > max_long_edge:
        scale = min(scale, max_long_edge / float(max(width, height)))
    if scale < 1.0:
        size = (max(1, int(width * scale)), max(1, int(height * scale)))
        return image.resize(size, Image.Resampling.LANCZOS)
    return image


def _encoding_metadata(image, exif, icc_profile):
    """Retain source metadata while refreshing dimensions already present in EXIF."""
    metadata = {}
    if icc_profile:
        metadata["icc_profile"] = icc_profile
    # Orientation has already been applied by exif_transpose.
    # Keep the remaining EXIF and update existing dimension tags.
    for tag, value in (
        (256, image.width),
        (257, image.height),
        (40962, image.width),
        (40963, image.height),
    ):
        if tag in exif:
            exif[tag] = value
    if 34665 in exif:
        exif_ifd = exif.get_ifd(34665)
        for tag, value in ((40962, image.width), (40963, image.height)):
            if tag in exif_ifd:
                exif_ifd[tag] = value
    if exif:
        metadata["exif"] = exif.tobytes()
    return metadata


def encode_image(
    source,
    *,
    allocate_output: Callable[[], Path],
    extension: str,
    quality: int | Callable[[], int],
    max_long_edge=None,
    max_height=None,
    preserve_alpha=True,
):
    """Encode using EXIF orientation, ICC conversion and existing Pillow settings.

    Quality may be selected lazily after reading source metadata. allocate_output
    is called after pixel preparation; its owner allocates an exclusive stage and
    owns cleanup/publication. This function closes input before returning.
    """
    with Image.open(source) as image:
        image = ImageOps.exif_transpose(image)
        icc_profile = image.info.get("icc_profile")
        exif = image.getexif()
        quality = quality() if callable(quality) else quality

        image, icc_profile = _prepare_pixels(image, extension, preserve_alpha, icc_profile)
        image = _downscale(image, max_long_edge, max_height)
        staged_path = allocate_output()
        metadata = _encoding_metadata(image, exif, icc_profile)

        if extension in (".jpg", ".jpeg"):
            image.save(staged_path, "JPEG", quality=quality, optimize=True, **metadata)
        elif extension == ".webp":
            image.save(staged_path, "WEBP", quality=quality, method=6, **metadata)
        else:
            raise UnsupportedImageFormat(extension)


def image_is_color(source, *, chroma_std_threshold=2.5, sample_max=512):
    """Classify grayscale versus chroma, including uniform tints and JPEG noise."""
    with Image.open(source) as img:
        # Fast path for obvious grayscale modes
        if img.mode in ("1", "L", "LA"):
            return False

        # Normalize to YCbCr
        ycbcr = img.convert("YCbCr")

        # Optional downscale for speed on huge images
        w, h = ycbcr.size
        m = max(w, h)
        if m > sample_max:
            scale = sample_max / float(m)
            ycbcr = ycbcr.resize(
                (max(1, int(w * scale)), max(1, int(h * scale))), Image.BILINEAR
            )

        _, cb, cr = ycbcr.split()
        cb_stats = ImageStat.Stat(cb)
        cr_stats = ImageStat.Stat(cr)

        # Keep the existing variation test and tolerance, and also detect
        # uniform color/tints whose chroma is offset from neutral.
        is_color = any(
            channel.stddev[0] > chroma_std_threshold
            or abs(channel.mean[0] - 128) > chroma_std_threshold
            for channel in (cb_stats, cr_stats)
        )
        return is_color
