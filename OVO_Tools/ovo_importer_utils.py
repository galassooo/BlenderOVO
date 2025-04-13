# --------------------------------------------------------
#  OVO IMPORTER UTILS
# --------------------------------------------------------
# This module provides pure utility functions that are used by
# the importer. It includes:
#   - half_to_float: Converts a 16-bit half-precision float to a Python float.
#   - decode_half2x16: Extracts two 16-bit half-floats (for UV data).
#   - read_null_terminated_string: Reads a C-style string from a binary file.
#   - flip_image_vertically: flips the image vertically.
#
# These functions do not depend on Blender and help keep the main parser
# code clean and modular.
# ================================================================

import struct
import numpy as np


def half_to_float(h: int) -> float:
    """
    Convert a 16-bit half-precision float (stored as an int) to a Python float.

    The half precision float is represented with:
      - 1 bit for sign
      - 5 bits for exponent
      - 10 bits for fraction

    :param h: The 16-bit integer representing the half-precision float.
    :return: A 32-bit floating point value.
    """
    s = (h >> 15) & 0x0001  # Extract sign bit
    e = (h >> 10) & 0x001F  # Extract exponent bits (5 bits)
    f = h & 0x03FF  # Extract fraction bits (10 bits)

    if e == 0:
        # Denormalized number (or zero)
        val = (f / 1024.0) * (2 ** -14)
    elif e == 31:
        # Inf or NaN
        val = float('inf') if f == 0 else float('nan')
    else:
        # Normalized number
        val = (1 + f / 1024.0) * (2 ** (e - 15))

    return -val if s == 1 else val


def decode_half2x16(packed_uv: int):
    """
    Decode two 16-bit half-precision floats packed into a single 32-bit integer.

    This is typically used to extract UV coordinate pairs from a single packed value.

    :param packed_uv: 32-bit integer containing two half-floats.
    :return: A tuple (u, v) as Python floats.
    """
    # Pack the integer into 4 bytes, then unpack as two unsigned shorts (16-bit)
    raw_bytes = struct.pack('<I', packed_uv)
    h1, h2 = struct.unpack('<HH', raw_bytes)
    return (half_to_float(h1), half_to_float(h2))


def read_null_terminated_string(file_obj) -> str:
    """
    Read a null-terminated (C-style) string from a binary file-like object.

    The function reads byte-by-byte until it encounters a null byte (b'\x00'),
    then decodes the bytes to a UTF-8 string.

    :param file_obj: A binary file-like object.
    :return: The decoded string.
    """
    chars = []
    while True:
        c = file_obj.read(1)
        if not c or c == b'\x00':
            break
        chars.append(c)
    return b''.join(chars).decode('utf-8', errors='replace')


import bpy, numpy as np


def create_flipped_image(image):
    """
    Create and return a flipped copy of the given image.
    The copy will contain the vertically flipped pixel data.

    :param image: The original bpy.types.Image instance.
    :return: A new bpy.types.Image instance with pixels flipped vertically.
    """
    try:
        width, height = image.size
        channels = image.channels  # Use the actual channel count (commonly 4 for RGBA)
        total = width * height * channels

        # Create a Python list and retrieve pixels using foreach_get
        pixels = [0.0] * total
        image.pixels.foreach_get(pixels)

        # Convert to NumPy array and reshape to a 3D array (height, width, channels)
        arr = np.array(pixels, dtype=np.float32).reshape((height, width, channels))

        # Flip the array vertically
        arr = np.flipud(arr)

        # Create a new image to hold the flipped pixel data;
        # give it a distinct name (or append a suffix)
        new_image_name = image.name + "_flipped"
        new_image = bpy.data.images.new(new_image_name, width, height, alpha=(channels == 4))

        # Write the flipped pixel data back into the new image
        new_image.pixels.foreach_set(arr.flatten().tolist())
        new_image.update()

        # Optionally, store a custom property to mark it as already flipped
        new_image["flipped"] = True

        return new_image
    except Exception as e:
        print(f"[create_flipped_image] Error flipping image '{image.name}': {e}")
        return image
