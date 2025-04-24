# ================================================================
# TEXTURE MANAGER
# ================================================================
# Handles texture conversion, compression, flipping, and exporting
# for materials within the OVO exporter pipeline.
# ================================================================

# --------------------------------------------------------
# IMPORTS
# --------------------------------------------------------
import bpy
import os
import platform
import subprocess
import numpy as np
import shutil

try:
    from .ovo_texture_flipper import OVOTextureFlipper
    from .ovo_log import log
except ImportError:
    from ovo_texture_flipper import OVOTextureFlipper
    from ovo_log import log

# --------------------------------------------------------
# OVO Texture Manager
# --------------------------------------------------------
class OVOTextureManager:
    """
    Class that manages texture operations for the OVO format.
    Handles compression, conversion, flipping, and texture tracking.
    """

    def __init__(self, export_path, use_legacy_compression=True, flip_textures=True):
        """
        Initializes the texture manager.

        Args:
            export_path (str): Path of the output OVO file
            use_legacy_compression (bool): If True, uses S3TC compression (DXT1/DXT5),
                                           otherwise uses BPTC (BC7)
            flip_textures (bool): If True, flips textures vertically during export
        """
        self.export_directory = os.path.dirname(export_path)
        self.use_legacy_compression = use_legacy_compression
        self.flip_textures = flip_textures
        self.addon_directory = os.path.dirname(os.path.abspath(__file__))
        self.processed_textures = {}

        # Create export directory if it doesn't exist
        if not os.path.exists(self.export_directory):
            try:
                os.makedirs(self.export_directory)
                log(f"[OVOTextureManager] Created export directory: {self.export_directory}", category="TEXTURE")
            except Exception as e:
                log(f"[OVOTextureManager] WARNING: Could not create export directory: {str(e)}", category="WARNING")

    # --------------------------------------------------------
    # Copy Texture Without Compression
    # --------------------------------------------------------
    def copy_texture_without_compression(self, input_path, output_name=None):
        """
        Copies a texture without compression when compression is not available.

        Args:
            input_path (str): Path of the original texture
            output_name (str, optional): Output file name

        Returns:
            str: Name of the copied file or "[none]" in case of error
        """
        if output_name is None:
            output_name = os.path.basename(input_path)

        # Destination in the same folder as the OVO export
        output_path = os.path.join(self.export_directory, output_name)

        try:
            # Copy the texture
            shutil.copy2(input_path, output_path)
            log(f"[OVOTextureManager] Texture copied without compression: '{output_name}'", category="TEXTURE")

            # If flipping is enabled and it's a DDS file, try to flip it
            if self.flip_textures and output_path.lower().endswith('.dds'):
                if OVOTextureFlipper.is_dds_file(output_path):
                    try:
                        flipped_path = output_path
                        OVOTextureFlipper.flip_dds_texture(output_path, flipped_path)
                        log(f"[OVOTextureManager] Texture flipped in place: '{output_name}'", category="TEXTURE")
                    except Exception as e:
                        log(f"[OVOTextureManager] WARNING: Failed to flip texture: {str(e)}", category="WARNING")

            return output_name
        except Exception as e:
            log(f"[OVOTextureManager] ERROR: Failed to copy texture: {str(e)}", category="ERROR")
            return "[none]"

    # --------------------------------------------------------
    # Compress Texture to DDS
    # --------------------------------------------------------
    def compress_texture_to_dds(self, input_path, output_path=None, isAlbedo=False):
        """
        Compresses a texture to DDS format using the appropriate compressor for the platform.

        Args:
            input_path (str): Path of the original texture
            output_path (str, optional): Output path for the DDS file
            isAlbedo (bool): If True, it's a texture with alpha channel, otherwise it's a normal map or other

        Returns:
            tuple: (bool, str) Indicates if compression was successful and the path of the compressed file
        """
        if not os.path.exists(input_path):
            log(f"[OVOTextureManager] ERROR: Input texture does not exist: '{input_path}'", category="ERROR")
            return False, None

        # Check if the texture has already been processed
        if input_path in self.processed_textures:
            log(f"[OVOTextureManager] Using cached texture: '{self.processed_textures[input_path]}'", category="TEXTURE")
            return True, self.processed_textures[input_path]

        if output_path is None:
            output_path = os.path.splitext(input_path)[0] + ".dds"

        log(f"[OVOTextureManager] Converting texture: '{os.path.basename(input_path)}'", category="TEXTURE")
        log(f"- Target: '{os.path.basename(output_path)}'", category="TEXTURE", indent=1)
        log(f"- Type: {'Albedo' if isAlbedo else 'Non-Albedo'}", category="TEXTURE", indent=1)
        log(f"- Using legacy compression: {self.use_legacy_compression}", category="TEXTURE", indent=1)
        log(f"- Flip textures: {self.flip_textures}", category="TEXTURE", indent=1)

        # Determine operating system
        system = platform.system()

        # Determine format based on use_legacy_compression flag and texture type
        format = "dxt1"  # Default format
        try:
            if isAlbedo:
                try:
                    # Load image as binary bytes array
                    with open(input_path, 'rb') as f:
                        binary_data = f.read()

                    # Convert to a NumPy array of uint8
                    binary_array = np.frombuffer(binary_data, dtype=np.uint8)

                    if len(binary_array) % 4 == 0:
                        pixel_count = len(binary_array) // 4
                        arr = binary_array.reshape(pixel_count, 4)

                        def has_alpha_channel(arr):
                            """Checks if the image has a significant alpha channel."""
                            alpha_channel = arr[:, 3]
                            return not np.all(alpha_channel == 255)

                        # Choose format based on compression type and alpha presence
                        if self.use_legacy_compression:
                            format = "dxt5" if has_alpha_channel(arr) else "dxt1"
                            log(f"- Alpha channel detected: {has_alpha_channel(arr)}", category="TEXTURE", indent=1)
                        else:
                            format = "bc7"  # BC7 handles both with and without alpha
                    else:
                        # Otherwise fallback to format without alpha
                        format = "dxt1" if self.use_legacy_compression else "bc7"

                except Exception as e:
                    log(f"WARNING: Image analysis failed: {str(e)}", category="WARNING")
                    log(f"- Using default format for albedo: {'dxt1' if self.use_legacy_compression else 'bc7'}",category="WARNING", indent=1)
                    format = "dxt1" if self.use_legacy_compression else "bc7"
            else:
                format = "bc5"  # BC5 for normal maps
        except Exception as e:
            log(f"[OVOTextureManager] WARNING: Format detection failed: {str(e)}", category="WARNING")
            log(f"- Using fallback format: dxt1", category="WARNING", indent=1)

        log(f"- Selected format: {format.upper()}", category="TEXTURE", indent=1)

        # Get appropriate executable path for the platform
        result = self._compress_texture_for_platform(system, input_path, output_path, format)

        if result[0]:
            compressed_path = result[1]

            if self.flip_textures:
                log(f"- Flipping texture vertically", category="TEXTURE", indent=1)
                try:
                    # Use same path to overwrite the original file
                    flipped_path = OVOTextureFlipper.flip_dds_texture(compressed_path, compressed_path)
                    log(f"- Texture flipped successfully", category="TEXTURE", indent=1)
                except Exception as e:
                    log(f"WARNING: Failed to flip texture: {str(e)}", category="WARNING", indent=1)
                    log(f"- Original unflipped texture will be used", category="WARNING", indent=1)

            # Add to cache
            self.processed_textures[input_path] = compressed_path
            log(f"Compression successful: '{os.path.basename(compressed_path)}'", category="TEXTURE")
            return True, compressed_path
        else:
            log(f"[OVOTextureManager] Compression failed for '{os.path.basename(input_path)}'", category="WARNING")
            log(f"- Falling back to copy without compression", category="WARNING", indent=1)

            # Fallback to plain copy if compression fails
            output_name = os.path.basename(output_path)
            copied_name = self.copy_texture_without_compression(input_path, output_name)

            if copied_name != "[none]":
                copied_path = os.path.join(self.export_directory, copied_name)
                self.processed_textures[input_path] = copied_path
                return True, copied_path

            return False, None

    # --------------------------------------------------------
    # Compress Texture for Platform
    # --------------------------------------------------------
    def _compress_texture_for_platform(self, system, input_path, output_path, format):
        """
        Executes the texture compression for the specified platform.

        Args:
            system (str): Operating system
            input_path (str): Path of the original texture
            output_path (str): Output path for the DDS file
            format (str): Compression format

        Returns:
            tuple: (bool, str) Indicates if compression was successful and the path of the compressed file
        """
        log(f"Compressing for platform: {system}", category="")

        # Make sure output directory exists
        output_dir = os.path.dirname(output_path)
        if not os.path.exists(output_dir):
            try:
                os.makedirs(output_dir)
                log(f"Created output directory: {output_dir}", category="", indent=1)
            except Exception as e:
                log(f"ERROR: Failed to create output directory: {str(e)}", category="ERROR", indent=1)
                return False, None

        # Compression on macOS
        if system == "Darwin":  # macOS
            compressor_path = os.path.join(self.addon_directory, "bin", "dds_compress")

            # Check that the executable exists
            if not os.path.exists(compressor_path):
                log(f"[OVOTextureManager] ERROR: Executable not found at '{compressor_path}'", category="ERROR", indent=1)
                return False, None

            # On macOS, make the executable executable
            os.chmod(compressor_path, 0o755)

            # Run the compressor
            try:
                cmd = [compressor_path, input_path, output_path, format.lower()]

                result = subprocess.run(
                    cmd,
                    check=True,
                    capture_output=True,
                    text=True
                )

                if result.returncode == 0:
                    log("Compression successful", category="TEXTURE", indent=1)
                    return True, output_path
                else:
                    log(f"Compression error: {result.stderr}", category="ERROR", indent=1)
                    return False, None
            except Exception as e:
                log(f"ERROR: Failed to execute compressor: {str(e)}", category="ERROR", indent=1)
                return False, None

        # Compression on Windows
        elif system == "Windows":
            compressor_path = os.path.join(self.addon_directory, "bin", "CompressonatorCLI.exe")

            # Check that the executable exists
            if not os.path.exists(compressor_path):
                log(f"ERROR: Compressonator CLI not found at '{compressor_path}'", category="ERROR", indent=1)
                log("Download Compressonator from https://github.com/GPUOpen-Tools/Compressonator/releases",category="TEXTURE", indent=2)
                log("Place CompressonatorCLI.exe in the bin folder of the addon", category="TEXTURE", indent=2)
                return False, None

            # Map formats to compressonator format
            format_map = {
                "dxt1": "BC1",
                "dxt5": "BC3",
                "bc5": "BC5",
                "bc7": "BC7"
            }

            comp_format = format_map.get(format.lower(), "BC7")

            # Build command for Compressonator
            cmd = [
                compressor_path,
                "-fd", comp_format,
                input_path,
                output_path
            ]

            try:
                result = subprocess.run(
                    cmd,
                    check=True,
                    capture_output=True,
                    text=True
                )

                if result.returncode == 0:
                    log("Compression successful", category="TEXTURE", indent=1)
                    return True, output_path
                else:
                    log(f"Compressonator error: {result.stderr}", category="ERROR", indent=1)
                    return False, None
            except Exception as e:
                log(f"ERROR: Failed to execute Compressonator: {str(e)}", category="ERROR", indent=1)
                return False, None

        # Support for Linux
        elif system == "Linux":
            compressor_path = os.path.join(self.addon_directory, "bin", "dds_compress_linux")

            if not os.path.exists(compressor_path):
                log(f"[OVOTextureManager] ERROR: Compressor not found for Linux at '{compressor_path}'", category="ERROR", indent=1)
                return False, None

            # For Linux, make the executable executable
            os.chmod(compressor_path, 0o755)

            # Map formats to compressonator format for Linux
            format_map = {
                "dxt1": "BC1",
                "dxt5": "BC3",
                "bc5": "BC5",
                "bc7": "BC7"
            }

            comp_format = format_map.get(format.lower(), "BC7")

            # Command for Linux Compressonator
            cmd = [
                compressor_path,
                "-fd", comp_format,
                input_path,
                output_path
            ]

            try:
                result = subprocess.run(
                    cmd,
                    check=True,
                    capture_output=True,
                    text=True
                )

                if result.returncode == 0:
                    log("Compression successful", category="TEXTURE", indent=1)
                    return True, output_path
                else:
                    log(f"Compression error: {result.stderr}", category="ERROR", indent=1)
                    return False, None
            except Exception as e:
                log(f"ERROR: Failed to execute compressor: {str(e)}", category="ERROR", indent=1)
                return False, None

        else:
            log(f"[OVOTextureManager] ERROR: Unsupported operating system: {system}", category="ERROR", indent=1)
            return False, None

    # --------------------------------------------------------
    # Trace to Image Node
    # --------------------------------------------------------
    def trace_to_image_node(self, input_item, isAlbedo=False):
        """
        Recursive function to trace up the node chain to the image texture node,
        also handling intermediate nodes (e.g. Bright/Contrast).

        Args:
            input_item: Input socket or node from which to start the search
            isAlbedo (bool): If True, the texture is an albedo/color texture

        Returns:
            str: Name of the processed texture or "[none]" if not found
        """
        # If the element doesn't have the is_linked attribute, it might be a node;
        # in this case, take the "Color" socket if present.
        if not hasattr(input_item, "is_linked"):
            input_item = input_item.inputs.get("Color")
            if not input_item:
                return "[none]"

        # If the socket is not linked, exit
        if not input_item or not input_item.is_linked:
            return "[none]"

        # Get the source socket and related node
        from_socket = input_item.links[0].from_socket
        from_node = from_socket.node
        log(f"[OVOTextureManager] Tracing from input: '{input_item.name}'", category="TEXTURE", indent=1)
        log(f"Connected node type: {type(from_node).__name__}", category="TEXTURE", indent=2)

        # Base case: if the node is an Image Texture, save the texture
        if isinstance(from_node, bpy.types.ShaderNodeTexImage):
            log("Found Image Texture node directly", category="TEXTURE", indent=2)
            if from_node.image:
                image = from_node.image
                log(f"Image name: '{image.name}'", category="TEXTURE", indent=2)
                # If the image is packed, save it to the output folder
                if image.packed_file:
                    texture_filename = image.name
                    output_path = os.path.join(self.export_directory, texture_filename)
                    try:
                        image.save_render(output_path)
                        log(f"Saved packed image to: '{output_path}'", category="TEXTURE", indent=2)
                        # Now compress the texture to DDS
                        dds_output = os.path.splitext(output_path)[0] + ".dds"
                        success, dds_path = self.compress_texture_to_dds(
                            output_path,
                            dds_output,
                            isAlbedo=isAlbedo
                        )
                        if success:
                            os.remove(output_path)  # Remove original file after compression
                            texture_name_dds = os.path.splitext(os.path.basename(dds_path))[0] + ".dds"
                            return texture_name_dds
                        else:
                            # Fallback: use uncompressed texture
                            log("Compression failed, using uncompressed texture", category="WARNING", indent=2)
                            return self.copy_texture_without_compression(output_path)
                    except Exception as e:
                        log(f"ERROR: Failed to export texture '{texture_filename}': {e}", category="ERROR", indent=2)
                        return "[none]"

                # For the case of images with filepath:
                elif image.filepath:
                    source_path = bpy.path.abspath(image.filepath)
                    if os.path.exists(source_path):
                        texture_filename = os.path.basename(source_path)
                        output_path = os.path.join(self.export_directory, texture_filename)
                        try:
                            log(f"Using image from filepath: '{source_path}'", category="TEXTURE", indent=2)
                            dds_output = os.path.splitext(output_path)[0] + ".dds"
                            success, dds_path = self.compress_texture_to_dds(
                                source_path,
                                dds_output,
                                isAlbedo=isAlbedo
                            )
                            if success:
                                texture_name_dds = os.path.splitext(os.path.basename(dds_path))[0] + ".dds"
                                return texture_name_dds
                            else:
                                # Fallback: use uncompressed texture
                                log("Compression failed, using uncompressed texture", category="WARNING", indent=2)
                                return self.copy_texture_without_compression(source_path)
                        except Exception as e:
                            log(f"ERROR: Failed to compress texture: {e}", category="ERROR", indent=2)
                            # Fallback: use uncompressed texture
                            return self.copy_texture_without_compression(source_path)
                    else:
                        log(f"ERROR: Image filepath does not exist: '{source_path}'", category="ERROR", indent=2)
            return "[none]"

        # If the node is not an Image Texture, try to trace through the "Color" socket
        if hasattr(from_node, 'inputs'):
            color_input = from_node.inputs.get('Color')
            if color_input and color_input.is_linked:
                log("Following 'Color' input connection...", category="TEXTURE", indent=2)
                return self.trace_to_image_node(color_input, isAlbedo=isAlbedo)
            # If there's no "Color", try all linked inputs
            for inp in from_node.inputs:
                if inp.is_linked:
                    log(f"Following '{inp.name}' input connection...", category="TEXTURE", indent=2)
                    result = self.trace_to_image_node(inp, isAlbedo=isAlbedo)
                    if result != "[none]":
                        return result

                log("No image found in node chain", category="TEXTURE", indent=2)
                return "[none]"