# ================================================================
# DDS TEXTURE FLIPPER
# ================================================================
# Handles vertical flipping of compressed DDS textures.
# Supports standard formats (DXT1, DXT5, BC5) and DX10 headers.
# Used during import/export for texture consistency in OVO files.
# ================================================================

# --------------------------------------------------------
# IMPORTS
# --------------------------------------------------------
import os
import struct
import shutil
import tempfile
import sys

try:
    from .ovo_log import log
except ImportError:
    from ovo_log import log

# --------------------------------------------------------
# OVO Texture Flipper
# --------------------------------------------------------
class OVOTextureFlipper:
    """
    Handles vertical flipping of DDS textures, used by the OVO pipeline.

    Supports standard DXT1, DXT5, BC5 formats, and extended DX10 headers.
    """

    # Compression format codes
    DXT1_FOURCC = b'DXT1'   # 8 bytes per block
    DXT5_FOURCC = b'DXT5'   # 16 bytes per block
    BC5_FOURCC = b'ATI2'    # 16 bytes per block (ATI2 is the FourCC code for BC5)
    BC5U_FOURCC = b'BC5U'   # Alternate code used for BC5
    BC5S_FOURCC = b'BC5S'   # Alternate code used for BC5
    DX10_FOURCC = b'DX10'   # Marker for extended DX10 header

    # Block size in bytes for each supported compression format
    BLOCK_SIZE = {
        DXT1_FOURCC: 8,     # 8 bytes per block
        DXT5_FOURCC: 16,    # 16 bytes per block
        BC5_FOURCC: 16,     # 16 bytes per block
        BC5U_FOURCC: 16,    # 16 bytes per block
        BC5S_FOURCC: 16     # 16 bytes per block
    }

    # DXGI_FORMAT values for common formats
    DXGI_FORMAT = {
        71: 'BC1_TYPELESS',     # 8 bytes per block
        72: 'BC1_UNORM',        # 8 bytes per block (DXT1)
        73: 'BC1_UNORM_SRGB',   # 8 bytes per block (DXT1)
        74: 'BC2_TYPELESS',     # 16 bytes per block
        75: 'BC2_UNORM',        # 16 bytes per block (DXT3)
        76: 'BC2_UNORM_SRGB',   # 16 bytes per block
        77: 'BC3_TYPELESS',     # 16 bytes per block
        78: 'BC3_UNORM',        # 16 bytes per block (DXT5)
        79: 'BC3_UNORM_SRGB',   # 16 bytes per block
        80: 'BC4_TYPELESS',     # 8 bytes per block
        81: 'BC4_UNORM',        # 8 bytes per block (BC4, 1 channel)
        82: 'BC4_SNORM',        # 8 bytes per block
        83: 'BC5_TYPELESS',     # 16 bytes per block
        84: 'BC5_UNORM',        # 16 bytes per block (BC5, 2 channels, ideal for normal maps)
        85: 'BC5_SNORM',        # 16 bytes per block (signed BC5)
        86: 'BC6H_TYPELESS',    # 16 bytes per block
        87: 'BC6H_UF16',        # 16 bytes per block (BC6H, HDR)
        88: 'BC6H_SF16',        # 16 bytes per block
        89: 'BC7_TYPELESS',     # 16 bytes per block
        90: 'BC7_UNORM',        # 16 bytes per block (BC7, high quality)
        91: 'BC7_UNORM_SRGB'    # 16 bytes per block
    }

    # DXGI Block Sizes
    DXGI_BLOCK_SIZE = {
        # BC1 (DXT1)
        71: 8, 72: 8, 73: 8,
        # BC2 (DXT3)
        74: 16, 75: 16, 76: 16,
        # BC3 (DXT5)
        77: 16, 78: 16, 79: 16,
        # BC4
        80: 8, 81: 8, 82: 8,
        # BC5
        83: 16, 84: 16, 85: 16,
        # BC6H
        86: 16, 87: 16, 88: 16,
        # BC7
        89: 16, 90: 16, 91: 16
    }

    # Header offsets
    HEIGHT_OFFSET = 12
    WIDTH_OFFSET = 16
    MIPMAP_COUNT_OFFSET = 28
    PITCH_OR_LINEAR_SIZE_OFFSET = 20
    FLAGS_OFFSET = 8  # dwFlags
    PIXEL_FORMAT_OFFSET = 76
    FOURCC_OFFSET = 84

    # DDS header flags
    DDSD_CAPS = 0x1
    DDSD_HEIGHT = 0x2
    DDSD_WIDTH = 0x4
    DDSD_PITCH = 0x8
    DDSD_PIXELFORMAT = 0x1000
    DDSD_MIPMAPCOUNT = 0x20000
    DDSD_LINEARSIZE = 0x80000

    # Pixel format flags
    DDPF_ALPHAPIXELS = 0x1
    DDPF_ALPHA = 0x2
    DDPF_FOURCC = 0x4
    DDPF_RGB = 0x40

    # Header size
    HEADER_SIZE = 128
    DX10_HEADER_SIZE = 20  # Header size for DX10

    # --------------------------------------------------------
    # Flip DDS Texture
    # --------------------------------------------------------
    @staticmethod
    def flip_dds_texture(input_path, output_path=None):
        """
        Vertically flips a DDS texture, supporting standard formats and DX10 headers.

        Args:
            input_path (str): Path to the DDS file to flip.
            output_path (str, optional): Output path. If None, overwrites the original file.

        Returns:
            str: Path to the flipped DDS file, or original file on error.
        """
        if not os.path.exists(input_path):
            log(f"File not found: {input_path}", category="ERROR")
            return input_path

        if output_path is None:
            temp_dir = tempfile.gettempdir()
            temp_file = os.path.join(temp_dir, f"temp_{os.path.basename(input_path)}")
            final_output = input_path
        else:
            temp_file = output_path
            final_output = output_path

        try:
            with open(input_path, 'rb') as f:
                data = f.read()

            if len(data) < OVOTextureFlipper.HEADER_SIZE or data[:4] != b'DDS ':
                raise ValueError(f"Il file {input_path}  is not a valid DDS file")

            # Extract header info
            header = data[:OVOTextureFlipper.HEADER_SIZE]
            width = struct.unpack('<I', data[OVOTextureFlipper.WIDTH_OFFSET:OVOTextureFlipper.WIDTH_OFFSET+4])[0]
            height = struct.unpack('<I', data[OVOTextureFlipper.HEIGHT_OFFSET:OVOTextureFlipper.HEIGHT_OFFSET+4])[0]
            flags = struct.unpack('<I', data[OVOTextureFlipper.FLAGS_OFFSET:OVOTextureFlipper.FLAGS_OFFSET+4])[0]
            has_mipmap = (flags & OVOTextureFlipper.DDSD_MIPMAPCOUNT) != 0
            mipmap_count = struct.unpack('<I', data[OVOTextureFlipper.MIPMAP_COUNT_OFFSET:OVOTextureFlipper.MIPMAP_COUNT_OFFSET+4])[0] if has_mipmap else 1

            pixel_format_flags = struct.unpack('<I', data[OVOTextureFlipper.PIXEL_FORMAT_OFFSET:OVOTextureFlipper.PIXEL_FORMAT_OFFSET+4])[0]
            four_cc = data[OVOTextureFlipper.FOURCC_OFFSET:OVOTextureFlipper.FOURCC_OFFSET+4]

            log(f"Flipping DDS: {os.path.basename(input_path)}", category="")
            log(f"  Size: {width}x{height}", category="", indent=1)
            log(f"  Mipmaps: {mipmap_count}", category="", indent=1)
            log(f"  FourCC: {four_cc.decode('ascii', errors='replace')}", category="", indent=1)

            # Check for DX10 header
            header_size = OVOTextureFlipper.HEADER_SIZE
            dxgi_format = None
            is_dx10 = False

            # Check per header DX10
            if four_cc == OVOTextureFlipper.DX10_FOURCC:
                is_dx10 = True
                header_size += OVOTextureFlipper.DX10_HEADER_SIZE  # Aggiungi dimensione header DX10

                dxgi_format = struct.unpack('<I', data[OVOTextureFlipper.HEADER_SIZE:OVOTextureFlipper.HEADER_SIZE+4])[0]
                log(f"  DX10 header detected. DXGI_FORMAT: {dxgi_format} ({OVOTextureFlipper.DXGI_FORMAT.get(dxgi_format, 'Unknown')})",category="", indent=1)

            block_size = None

            if is_dx10:
                if dxgi_format in OVOTextureFlipper.DXGI_BLOCK_SIZE:
                    block_size = OVOTextureFlipper.DXGI_BLOCK_SIZE[dxgi_format]
                    log(f"  Using block size: {block_size} bytes (DXGI_FORMAT: {OVOTextureFlipper.DXGI_FORMAT.get(dxgi_format)})",category="", indent=1)
                else:
                    raise ValueError(f"DXGI_FORMAT not supported: {dxgi_format}")
            else:
                if four_cc in OVOTextureFlipper.BLOCK_SIZE:
                    block_size = OVOTextureFlipper.BLOCK_SIZE[four_cc]
                    log(f"  Using block size: {block_size} bytes for format: {four_cc.decode('ascii', errors='replace')}",category="", indent=1)
                else:
                    if flags & OVOTextureFlipper.DDSD_PITCH:
                        raise ValueError(f"Uncompressed format with pitch not supported")
                    elif flags & OVOTextureFlipper.DDSD_LINEARSIZE:
                        linear_size = struct.unpack('<I', data[OVOTextureFlipper.PITCH_OR_LINEAR_SIZE_OFFSET:OVOTextureFlipper.PITCH_OR_LINEAR_SIZE_OFFSET+4])[0]
                        width_blocks = (width + 3) // 4
                        height_blocks = (height + 3) // 4
                        total_blocks = width_blocks * height_blocks
                        if total_blocks > 0:
                            estimated_block_size = linear_size / total_blocks
                            if estimated_block_size <= 12:
                                block_size = 8
                            else:
                                block_size = 16
                            log(f"  Estimated block size: {estimated_block_size:.2f} → rounded to {block_size}", category="WARNING", indent=1)
                        else:
                            raise ValueError("Unable to determine block size")
                    else:
                        raise ValueError(f"Unsupported format: {four_cc}")

            # Prepare new file
            with open(temp_file, 'wb') as f:
                # Write header
                f.write(data[:header_size])

                # Current data position
                pos = header_size

                current_width, current_height = width, height

                for level in range(mipmap_count):
                    # Block size
                    width_blocks = max(1, (current_width + 3) // 4)
                    height_blocks = max(1, (current_height + 3) // 4)

                    mipmap_size = width_blocks * height_blocks * block_size

                    if pos + mipmap_size > len(data):
                        log(f"  WARNING: Mipmap {level} data appears incomplete", category="WARNING", indent=1)
                        f.write(data[pos:])
                        break

                    # Extract data from mipmap
                    mipmap_data = data[pos:pos+mipmap_size]

                    row_size = width_blocks * block_size

                    rows = []
                    for i in range(0, len(mipmap_data), row_size):
                        if i + row_size <= len(mipmap_data):
                            rows.append(mipmap_data[i:i+row_size])
                        else:
                            rows.append(mipmap_data[i:])

                    # Vertical flip
                    flipped_mipmap = b''.join(reversed(rows))

                    f.write(flipped_mipmap)

                    if level == 0:
                        log(f"  Base mipmap: {width_blocks}x{height_blocks} blocks ({row_size} bytes/row)",category="", indent=1)

                    pos += mipmap_size

                    current_width = max(1, current_width // 2)
                    current_height = max(1, current_height // 2)

                if pos < len(data):
                    remaining_data = data[pos:]
                    f.write(remaining_data)
                    log(f"  Copied {len(remaining_data)} extra bytes after mipmaps", category="", indent=1)

            if temp_file != final_output:
                shutil.move(temp_file, final_output)

            log(f"Texture successfully flipped: {final_output}", category="")
            return final_output

        except (IOError, ValueError) as e:
            log(f"ERROR during texture flipping: {str(e)}", category="ERROR")

            if temp_file != input_path and output_path is None:
                if os.path.exists(temp_file):
                    try:
                        os.remove(temp_file)
                    except:
                        pass
            return input_path
        except Exception as e:
            log(f"UNEXPECTED ERROR during texture flip: {str(e)}", category="ERROR")

            return input_path

    # --------------------------------------------------------
    # Check DDS File Validity
    # --------------------------------------------------------
    @staticmethod
    def is_dds_file(filepath):
        """
        Checks whether a file is a valid DDS texture.

        Args:
            filepath (str): Path to the file to check.

        Returns:
            bool: True if the file is a valid DDS, False otherwise.
        """
        try:
            with open(filepath, 'rb') as f:
                magic = f.read(4)
            return magic == b'DDS '
        except:
            return False

    # --------------------------------------------------------
    # Get DDS Texture Info
    # --------------------------------------------------------
    @staticmethod
    def get_dds_info(filepath):
        """
        Extracts basic information from a DDS file.

        Args:
            filepath (str): Path to the DDS file.

        Returns:
            dict: Dictionary with info (width, height, mipmap_count, format, dxgi_format if present),
                  or None if the file is not a valid DDS.
        """
        try:
            with open(filepath, 'rb') as f:
                data = f.read(148)

            if data[:4] != b'DDS ':
                return None

            width = struct.unpack('<I', data[OVOTextureFlipper.WIDTH_OFFSET:OVOTextureFlipper.WIDTH_OFFSET+4])[0]
            height = struct.unpack('<I', data[OVOTextureFlipper.HEIGHT_OFFSET:OVOTextureFlipper.HEIGHT_OFFSET+4])[0]
            flags = struct.unpack('<I', data[OVOTextureFlipper.FLAGS_OFFSET:OVOTextureFlipper.FLAGS_OFFSET+4])[0]
            has_mipmap = (flags & OVOTextureFlipper.DDSD_MIPMAPCOUNT) != 0
            mipmap_count = struct.unpack('<I', data[OVOTextureFlipper.MIPMAP_COUNT_OFFSET:OVOTextureFlipper.MIPMAP_COUNT_OFFSET+4])[0] if has_mipmap else 1
            four_cc = data[OVOTextureFlipper.FOURCC_OFFSET:OVOTextureFlipper.FOURCC_OFFSET+4]

            result = {
                'width': width,
                'height': height,
                'mipmap_count': mipmap_count,
                'format': four_cc
            }

            # If it is a DX10, extract the DXGI_FORMAT
            if four_cc == OVOTextureFlipper.DX10_FOURCC and len(data) >= OVOTextureFlipper.HEADER_SIZE + 4:
                dxgi_format = struct.unpack('<I', data[OVOTextureFlipper.HEADER_SIZE:OVOTextureFlipper.HEADER_SIZE+4])[0]
                result['dxgi_format'] = dxgi_format
                result['dxgi_format_name'] = OVOTextureFlipper.DXGI_FORMAT.get(dxgi_format, 'Unknown')

            return result
        except Exception as e:
            log(f"Error analyzing DDS file: {str(e)}", category="ERROR")
            return None

    # --------------------------------------------------------
    # Safe Texture Flip
    # --------------------------------------------------------
    @staticmethod
    def safe_flip_dds_texture(input_path, output_path=None):
        """
        A safe wrapper for flip_dds_texture that does not raise exceptions.

        Args:
            input_path (str): Path to the DDS texture to flip.
            output_path (str, optional): Output path. If None, will overwrite the original.

        Returns:
            tuple: (bool, str) → Success flag and resulting path.
        """
        if not input_path or not os.path.exists(input_path):
            return False, input_path

        try:
            # Flip the texture
            result_path = OVOTextureFlipper.flip_dds_texture(input_path, output_path)

            # Verify if the resulting file exists
            if result_path != input_path and os.path.exists(result_path):
                return True, result_path
            elif os.path.exists(input_path):
                return False, input_path
            else:
                return False, None
        except Exception as e:
            log(f"Exception in safe texture flip: {str(e)}", category="ERROR")
            return False, input_path


# --------------------------------------------------------
# Standalone Test Runner (for CLI use)
# --------------------------------------------------------
if __name__ == "__main__":

    if len(sys.argv) < 2:
        print("Utilizzo: python ovo_texture_flipper.py <percorso_file_dds> [percorso_output]")
        sys.exit(1)

    input_file = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else None

    flipper = OVOTextureFlipper()

    if flipper.is_dds_file(input_file):
        info = flipper.get_dds_info(input_file)
        if info:
            print(f"Texture: {input_file}")
            print(f"  Dimensioni: {info['width']}x{info['height']}")
            print(f"  Mipmaps: {info['mipmap_count']}")
            format_str = info['format'].decode('ascii', errors='replace')
            print(f"  Formato: {format_str}")

            if 'dxgi_format' in info:
                print(f"  DXGI_FORMAT: {info['dxgi_format']} ({info['dxgi_format_name']})")

        success, flipped_path = flipper.safe_flip_dds_texture(input_file, output_file)
        if success:
            print(f"Texture flippata con successo: {flipped_path}")
        else:
            print(f"Non è stato possibile flippare la texture: {flipped_path}")
    else:
        print(f"Il file {input_file} non è un file DDS valido.")