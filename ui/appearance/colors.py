"""Portable ARGB conversion, luminance contrast and accessible accent blending."""


def argb(value):
    value = 0xff000000 | int(value.lstrip('#'), 16)
    return value - 2**32


def contrast_ratio(first, second):
    def luminance(value):
        channels = [((value >> shift) & 255) / 255 for shift in (16, 8, 0)]
        channels = [channel / 12.92 if channel <= .04045 else ((channel + .055) / 1.055) ** 2.4 for channel in channels]
        return sum(a * b for a, b in zip(channels, (.2126, .7152, .0722)))
    low, high = sorted([luminance(first), luminance(second)])
    return (high + .05) / (low + .05)


def readable_accent(accent, foreground, background):
    """Keep the theme hue where possible, bringing small selected labels to 4.5:1."""
    for step in range(17):
        fraction = step / 16
        channels = [round(((accent >> shift) & 255) * (1 - fraction)
                          + ((foreground >> shift) & 255) * fraction) for shift in (16, 8, 0)]
        candidate = (255 << 24) | (channels[0] << 16) | (channels[1] << 8) | channels[2]
        if contrast_ratio(candidate, background) >= 4.5:
            return candidate - 2**32
    return foreground
