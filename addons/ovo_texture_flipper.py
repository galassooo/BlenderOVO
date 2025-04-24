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
import math
import shutil
import tempfile

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
    # Flip BC1 data block
    # --------------------------------------------------------
    @staticmethod
    def _flip_bc1_block(block: bytes) -> bytes:
        """Vertically flips a BC1 / DXT1 block (8 bytes)."""
        # byte 0-3 = color0 & color1 (remain unchanged)
        colour_hdr = block[:4]
        # byte 4-7 = 16 2-bit color indices (row-major, little-endian)
        idx = int.from_bytes(block[4:], 'little')
        # extract 4 rows of 8 bits each and flip their order
        r0 = (idx >>  0) & 0xFF
        r1 = (idx >>  8) & 0xFF
        r2 = (idx >> 16) & 0xFF
        r3 = (idx >> 24) & 0xFF
        flipped = (r3 | (r2 << 8) | (r1 << 16) | (r0 << 24))
        return colour_hdr + flipped.to_bytes(4, 'little')


    # --------------------------------------------------------
    # Flip BC3 data block (with alpha)
    # --------------------------------------------------------
    @staticmethod
    def _flip_bc3_alpha(block: bytes) -> bytes:
        """Vertically flips the 6 bytes of alpha indices used in DXT5 / BC3 / BC4 / BC5."""
        a_idx = int.from_bytes(block, 'little')  # 48-bit alpha index
        rows = [(a_idx >> (12 * i)) & 0xFFF for i in range(4)]
        flipped = sum(rows[i] << (12 * (3 - i)) for i in range(4))
        return flipped.to_bytes(6, 'little')

    # --------------------------------------------------------
    # Flip BC3 data block (without alpha)
    # --------------------------------------------------------
    @staticmethod
    def _flip_bc3_block(block: bytes) -> bytes:
        """Vertically flips a BC3 / DXT5 block (16 bytes)."""
        # 0-1 = alpha0/alpha1, 2-7 = alpha indices (48 bits)
        a0a1 = block[0:2]
        a_idx = OVOTextureFlipper._flip_bc3_alpha(block[2:8])
        # 8-15 = color block (same structure as BC1)
        colour = OVOTextureFlipper._flip_bc1_block(block[8:])
        return a0a1 + a_idx + colour

    # --------------------------------------------------------
    # Flip BC5 data block (with alpha)
    # --------------------------------------------------------
    @staticmethod
    def _flip_bc5_block(block: bytes) -> bytes:
        """Vertically flips a BC5 block (16 bytes = R-channel + G-channel)."""
        # 0-7   = R channel (similar to alpha block in BC3)
        # 8-15  = G channel (same format)
        r_part = block[:8]
        g_part = block[8:]
        r_flipped = r_part[:2] + OVOTextureFlipper._flip_bc3_alpha(r_part[2:])
        g_flipped = g_part[:2] + OVOTextureFlipper._flip_bc3_alpha(g_part[2:])
        return r_flipped + g_flipped

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
            log(f"File does not exist: {input_path}", category="ERROR")
            return input_path


        if output_path is None: #if no output is specified, overwrite the input file
            temp_dir = tempfile.gettempdir()  #create a copy
            temp_file = os.path.join(temp_dir, f"temp_{os.path.basename(input_path)}")
            final_output = input_path
        else:
            temp_file = output_path
            final_output = output_path

        try:

            # Read file
            with open(input_path, 'rb') as f:
                data = f.read()

            # Verify input file is DDS
            if len(data) < OVOTextureFlipper.HEADER_SIZE or data[:4] != b'DDS ':
                raise ValueError(f"Il file {input_path} non è un file DDS valido")

            # Extract header information
            header = data[:OVOTextureFlipper.HEADER_SIZE]
            width = struct.unpack('<I', data[OVOTextureFlipper.WIDTH_OFFSET:OVOTextureFlipper.WIDTH_OFFSET+4])[0]
            height = struct.unpack('<I', data[OVOTextureFlipper.HEIGHT_OFFSET:OVOTextureFlipper.HEIGHT_OFFSET+4])[0]
            flags = struct.unpack('<I', data[OVOTextureFlipper.FLAGS_OFFSET:OVOTextureFlipper.FLAGS_OFFSET+4])[0]
            has_mipmap = (flags & OVOTextureFlipper.DDSD_MIPMAPCOUNT) != 0
            mipmap_count = struct.unpack('<I', data[OVOTextureFlipper.MIPMAP_COUNT_OFFSET:OVOTextureFlipper.MIPMAP_COUNT_OFFSET+4])[0] if has_mipmap else 1

            # Extract pixel infos
            pixel_format_flags = struct.unpack('<I', data[OVOTextureFlipper.PIXEL_FORMAT_OFFSET:OVOTextureFlipper.PIXEL_FORMAT_OFFSET+4])[0]
            four_cc = data[OVOTextureFlipper.FOURCC_OFFSET:OVOTextureFlipper.FOURCC_OFFSET+4]

            log(f"Flipping DDS: {os.path.basename(input_path)}", category="")
            log(f"  Size: {width}x{height}", category="", indent=1)
            log(f"  Mipmaps: {mipmap_count}", category="", indent=1)
            log(f"  FourCC: {four_cc.decode('ascii', errors='replace')}", category="", indent=1)

            # Determine if the DDS is a DX10 
            header_size = OVOTextureFlipper.HEADER_SIZE
            dxgi_format = None
            is_dx10 = False

            # Check for DX10 header
            if four_cc == OVOTextureFlipper.DX10_FOURCC:
                is_dx10 = True
                header_size += OVOTextureFlipper.DX10_HEADER_SIZE 

                # Extract DXGI_FORMAT from header
                dxgi_format = struct.unpack('<I', data[OVOTextureFlipper.HEADER_SIZE:OVOTextureFlipper.HEADER_SIZE+4])[0]
                log(f"  DX10 header detected. DXGI_FORMAT: {dxgi_format} ({OVOTextureFlipper.DXGI_FORMAT.get(dxgi_format, 'Unknown')})",category="", indent=1)

            # Determine block size basing on the type
            block_size = None

            if is_dx10:
                # If DX10, use DXGI format to determine size
                if dxgi_format in OVOTextureFlipper.DXGI_BLOCK_SIZE:
                    block_size = OVOTextureFlipper.DXGI_BLOCK_SIZE[dxgi_format]
                    log(f"  Using block size: {block_size} bytes (DXGI_FORMAT: {OVOTextureFlipper.DXGI_FORMAT.get(dxgi_format)})",category="", indent=1)
                else:
                    raise ValueError(f"DXGI_FORMAT non supportato: {dxgi_format}")
            else:
                # Use Four CC for other formats
                if four_cc in OVOTextureFlipper.BLOCK_SIZE:
                    block_size = OVOTextureFlipper.BLOCK_SIZE[four_cc]
                    log(f"  Using block size: {block_size} bytes for format: {four_cc.decode('ascii', errors='replace')}",category="", indent=1)
                else:
                    # For uncompressed formats or other formats, try to determine the size basing on pitch
                    if flags & OVOTextureFlipper.DDSD_PITCH:
                        raise ValueError(f"Formato non compresso con pitch non supportato")
                    elif flags & OVOTextureFlipper.DDSD_LINEARSIZE:
                        # Try to compute size by linear 
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
                            raise ValueError(f"Impossibile determinare la dimensione del blocco")
                    else:
                        raise ValueError(f"Formato non supportato: {four_cc}")

            # Write new file
            with open(temp_file, 'wb') as f:
            
                # Write header
                f.write(data[:header_size])

                pos = header_size

                # For each mipmap
                current_width, current_height = width, height
                for level in range(mipmap_count):

                    # Block size
                    width_blocks = max(1, (current_width + 3) // 4)
                    height_blocks = max(1, (current_height + 3) // 4)

                    # Level dimension
                    mipmap_size = width_blocks * height_blocks * block_size

                    # Ensure all data is available
                    if pos + mipmap_size > len(data):
                        log(f"  WARNING: Mipmap {level} data appears incomplete", category="WARNING", indent=1)
                        # copy data and exit
                        f.write(data[pos:])
                        break

                    # Extract data from mipmap
                    mipmap_data = data[pos:pos+mipmap_size]

                    # Calculate row length in block
                    row_size = width_blocks * block_size

                    # Divides data in rows
                    flipped_rows = []
                    for row in range(height_blocks): #From top to bottom
                        start = row * row_size
                        end   = start + row_size
                        row_data = mipmap_data[start:end]
                        new_row  = bytearray()

                        # Iterate through all row blocks
                        for col in range(width_blocks):
                            b_start = col * block_size
                            b_end   = b_start + block_size
                            blk = row_data[b_start:b_end]

                            # Flip block pixels depending on block size and type
                            if block_size == 8:
                                blk = OVOTextureFlipper._flip_bc1_block(blk)
                            else:  # 16 byte
                                if four_cc in (OVOTextureFlipper.DXT5_FOURCC,) or \
                                   dxgi_format in (77, 78, 79):
                                    blk = OVOTextureFlipper._flip_bc3_block(blk)
                                elif four_cc in (OVOTextureFlipper.BC5_FOURCC,
                                                  OVOTextureFlipper.BC5U_FOURCC,
                                                  OVOTextureFlipper.BC5S_FOURCC) or \
                                     dxgi_format in (83, 84, 85):
                                    blk = OVOTextureFlipper._flip_bc5_block(blk)
                                
                            new_row.extend(blk)

                        flipped_rows.append(bytes(new_row))

                    # Flip block orders
                    flipped_mipmap = b''.join(reversed(flipped_rows))

                    # Write flipped mipmap
                    f.write(flipped_mipmap)

                    # Detailed log only for first level:
                    if level == 0:
                        log(f"  Base mipmap: {width_blocks}x{height_blocks} blocks ({row_size} bytes/row)",category="", indent=1)

                    # Update cursor position to swith to the next mipmap level
                    pos += mipmap_size

                    # Divide by 2 dimension (mipmaps size are always / 2, eg. first original, second original/2, third original/4...)
                    current_width = max(1, current_width // 2)
                    current_height = max(1, current_height // 2)

                # If there are additional data copy them
                if pos < len(data):
                    remaining_data = data[pos:]
                    f.write(remaining_data)
                    log(f"  Copied {len(remaining_data)} extra bytes after mipmaps", category="", indent=1)

            # If we need to overwrite the orignal file, copy the flipped image over
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
