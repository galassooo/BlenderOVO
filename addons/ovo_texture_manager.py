import os
import platform
import subprocess
import numpy as np
import shutil
from pathlib import Path


class OVOTextureManager:
    """
    Class that manages texture operations for the OVO format.
    Handles compression, conversion and texture tracking.
    """

    def __init__(self, export_path, use_legacy_compression=True):
        """
        Initializes the texture manager.

        Args:
            export_path (str): Path of the output OVO file
            use_legacy_compression (bool): If True, uses S3TC compression (DXT1/DXT5),
                                           otherwise uses BPTC (BC7)
        """
        self.export_directory = os.path.dirname(export_path)
        self.use_legacy_compression = use_legacy_compression
        self.addon_directory = os.path.dirname(os.path.abspath(__file__))
        self.processed_textures = {}  # Cache of already processed textures

    def copy_texture_without_compression(self, input_path, output_name=None):
        """
        Copies a texture without compression when compression is not available.

        Args:
            input_path (str): Path of the original texture
            output_name (str, optional): Output file name

        Returns:
            str: Name of the copied file or "[none]" in case of error
        """
        # If no output name is specified, use the original file name
        if output_name is None:
            output_name = os.path.basename(input_path)

        # Destination in the same folder as the OVO export
        output_path = os.path.join(self.export_directory, output_name)

        try:
            # Copy the texture
            shutil.copy2(input_path, output_path)
            print(f"    [OVOTextureManager] Texture copied without compression: '{output_name}'")
            return output_name
        except Exception as e:
            print(f"    [OVOTextureManager] ERROR: Failed to copy texture: {str(e)}")
            return "[none]"

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
        # Check if the texture has already been processed
        if input_path in self.processed_textures:
            print(f"    [OVOTextureManager] Using cached texture: '{self.processed_textures[input_path]}'")
            return True, self.processed_textures[input_path]

        if output_path is None:
            output_path = os.path.splitext(input_path)[0] + ".dds"

        print(f"    [OVOTextureManager] Converting texture: '{os.path.basename(input_path)}'")
        print(f"      - Target: '{os.path.basename(output_path)}'")
        print(f"      - Type: {'Albedo' if isAlbedo else 'Non-Albedo'}")
        print(f"      - Using legacy compression: {self.use_legacy_compression}")

        # Determine operating system
        system = platform.system()

        # Determine format based on use_legacy_compression flag and texture type
        if isAlbedo:
            try:
                # Load image as binary bytes array
                with open(input_path, 'rb') as f:
                    binary_data = f.read()

                # Convert to a NumPy array of uint8
                binary_array = np.frombuffer(binary_data, dtype=np.uint8)

                # Assume it's an RGBA image
                if len(binary_array) % 4 == 0:
                    # Reshape assuming RGBA
                    pixel_count = len(binary_array) // 4
                    arr = binary_array.reshape(pixel_count, 4)

                    def has_alpha_channel(arr):
                        """Checks if the image has a significant alpha channel."""
                        alpha_channel = arr[:, 3]
                        return not np.all(alpha_channel == 255)

                    # Choose format based on compression type and alpha presence
                    if self.use_legacy_compression:
                        format = "dxt5" if has_alpha_channel(arr) else "dxt1"
                        print(f"      - Alpha channel detected: {has_alpha_channel(arr)}")
                    else:
                        format = "bc7"  # BC7 handles both with and without alpha
                else:
                    # Otherwise fallback to format without alpha
                    format = "dxt1" if self.use_legacy_compression else "bc7"

            except Exception as e:
                print(f"    [OVOTextureManager] ERROR: Image analysis failed: {str(e)}")
                return False, None
        else:
            # For normal maps or other special textures
            format = "bc5"  # BC5 for normal maps

        print(f"      - Selected format: {format.upper()}")

        # Get appropriate executable path for the platform
        result = self._compress_texture_for_platform(system, input_path, output_path, format)

        if result[0]:
            # Add to cache
            self.processed_textures[input_path] = result[1]
            print(f"    [OVOTextureManager] Compression successful: '{os.path.basename(result[1])}'")
        else:
            print(f"    [OVOTextureManager] Compression failed for '{os.path.basename(input_path)}'")

        return result

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
        print(f"    [OVOTextureManager] Compressing for platform: {system}")

        # Compression on macOS
        if system == "Darwin":  # macOS
            compressor_path = os.path.join(self.addon_directory, "bin", "dds_compress")

            # Check that the executable exists
            if not os.path.exists(compressor_path):
                print(f"    [OVOTextureManager] ERROR: Executable not found at '{compressor_path}'")
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
                    print(f"      - Compression successful")
                    return True, output_path
                else:
                    print(f"      - Compression error: {result.stderr}")
                    return False, None
            except Exception as e:
                print(f"      - ERROR: Failed to execute compressor: {str(e)}")
                return False, None

        # Compression on Windows
        elif system == "Windows":
            compressor_path = os.path.join(self.addon_directory, "bin", "CompressonatorCLI.exe")

            # Check that the executable exists
            if not os.path.exists(compressor_path):
                print(f"    [OVOTextureManager] ERROR: Compressonator CLI not found at '{compressor_path}'")
                print("      Download Compressonator from https://github.com/GPUOpen-Tools/Compressonator/releases")
                print("      and place CompressonatorCLI.exe in the bin folder of the addon")
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
                    print(f"      - Compression successful")
                    return True, output_path
                else:
                    print(f"      - Compressonator error: {result.stderr}")
                    return False, None
            except Exception as e:
                print(f"      - ERROR: Failed to execute Compressonator: {str(e)}")
                return False, None

        # Support for Linux
        elif system == "Linux":
            compressor_path = os.path.join(self.addon_directory, "bin", "dds_compress_linux")

            if not os.path.exists(compressor_path):
                print(f"    [OVOTextureManager] ERROR: Compressor not found for Linux at '{compressor_path}'")
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
                    print(f"      - Compression successful")
                    return True, output_path
                else:
                    print(f"      - Compression error: {result.stderr}")
                    return False, None
            except Exception as e:
                print(f"      - ERROR: Failed to execute compressor: {str(e)}")
                return False, None

        else:
            print(f"    [OVOTextureManager] ERROR: Unsupported operating system: {system}")
            return False, None

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
        import bpy

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
        print(f"    [OVOTextureManager] Tracing from input: '{input_item.name}'")
        print(f"      - Connected node type: {type(from_node).__name__}")

        # Base case: if the node is an Image Texture, save the texture
        if isinstance(from_node, bpy.types.ShaderNodeTexImage):
            print("      - Found Image Texture node directly")
            if from_node.image:
                image = from_node.image
                print(f"      - Image name: '{image.name}'")
                # If the image is packed, save it to the output folder
                if image.packed_file:
                    texture_filename = image.name
                    output_path = os.path.join(self.export_directory, texture_filename)
                    try:
                        image.save_render(output_path)
                        print(f"      - Saved packed image to: '{output_path}'")
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
                            print("      - Compression failed, using uncompressed texture")
                            return self.copy_texture_without_compression(output_path)
                    except Exception as e:
                        print(f"      - ERROR: Failed to export texture '{texture_filename}': {e}")
                        return "[none]"

                # For the case of images with filepath:
                elif image.filepath:
                    source_path = bpy.path.abspath(image.filepath)
                    if os.path.exists(source_path):
                        texture_filename = os.path.basename(source_path)
                        output_path = os.path.join(self.export_directory, texture_filename)
                        try:
                            print(f"      - Using image from filepath: '{source_path}'")
                            dds_output = os.path.splitext(output_path)[0] + ".dds"
                            success, dds_path = self.compress_texture_to_dds(
                                source_path,
                                dds_output,
                                isAlbedo=isAlbedo
                            )
                            if success:
                                # Hardcode the name in DDS: even if dds_path might already have the extension, ensure it's ".dds"
                                texture_name_dds = os.path.splitext(os.path.basename(dds_path))[0] + ".dds"
                                return texture_name_dds
                            else:
                                # Fallback: use uncompressed texture
                                print("      - Compression failed, using uncompressed texture")
                                return self.copy_texture_without_compression(source_path)
                        except Exception as e:
                            print(f"      - ERROR: Failed to compress texture: {e}")
                            # Fallback: use uncompressed texture
                            return self.copy_texture_without_compression(source_path)
            return "[none]"

        # If the node is not an Image Texture, try to trace through the "Color" socket
        if hasattr(from_node, 'inputs'):
            color_input = from_node.inputs.get('Color')
            if color_input and color_input.is_linked:
                print("      - Following 'Color' input connection...")
                return self.trace_to_image_node(color_input, isAlbedo=isAlbedo)
            # If there's no "Color", try all linked inputs
            for inp in from_node.inputs:
                if inp.is_linked:
                    print(f"      - Following '{inp.name}' input connection...")
                    result = self.trace_to_image_node(inp, isAlbedo=isAlbedo)
                    if result != "[none]":
                        return result

        print("      - No image found in node chain")
        return "[none]"