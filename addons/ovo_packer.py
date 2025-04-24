# ================================================================
# OVO PACKER
# ================================================================
# Utility class for serializing data into the binary OVO format.
# Handles writing matrices, vectors, normals, UVs and chunk headers.
# This class is used only during export.
# ================================================================

# --------------------------------------------------------
# IMPORTS
# --------------------------------------------------------
import math
import struct
import mathutils

try:
    from .ovo_log import log
except ImportError:
    from ovo_log import log

# --------------------------------------------------------
# OVO PACKER
# --------------------------------------------------------
class OVOPacker:
    """
    Class that handles data packing operations for the OVO format.
    Separates data serialization logic from export logic.
    """

    # --------------------------------------------------------
    # Pack String
    # --------------------------------------------------------
    @staticmethod
    def pack_string(string):
        """
        Packs a string in UTF-8 format with null terminator.

        Args:
            string (str): The string to pack

        Returns:
            bytes: The string encoded in UTF-8 with null terminator
        """
        return string.encode('utf-8') + b'\0'

     # --------------------------------------------------------
    # Pack Matrix
    # --------------------------------------------------------
    @staticmethod
    def pack_matrix(matrix):
        """
        Packs a 4x4 matrix in binary format.
        Performs matrix transposition for compatibility with OpenGL.

        Args:
            matrix (mathutils.Matrix): 4x4 matrix to pack

        Returns:
            bytes: Matrix packed as 16 consecutive floats
        """
        matrix = matrix.transposed()
        packed = struct.pack('16f', *[x for row in matrix for x in row])
        return packed

    # --------------------------------------------------------
    # Pack Vector3
    # --------------------------------------------------------
    @staticmethod
    def pack_vector3(vector):
        """
        Packs a 3D vector in binary format.

        Args:
            vector (mathutils.Vector): 3D vector to pack

        Returns:
            bytes: Vector packed as 3 consecutive floats
        """
        return struct.pack('3f', vector.x, vector.y, vector.z)

    # --------------------------------------------------------
    # Pack Normal
    # --------------------------------------------------------
    @staticmethod
    def pack_normal(normal):
        """
        Packs a normal vector using 10-10-10-2 format compatible with glm::packSnorm3x10_1x2

        Args:
            normal (mathutils.Vector): Normal vector to pack

        Returns:
            bytes: Normal packed in compressed format
        """
        # Ensure the normal vector is normalized
        normal = normal.normalized()

        def float_to_snorm10(f):
            # Limit to [-1, 1]
            f = max(-1.0, min(1.0, f))
            # Convert to [-511, 511] and handle sign
            if f >= 0:
                return int(f * 511.0 + 0.5)  # Added 0.5 for proper rounding
            else:
                return int(1024 + (f * 511.0 - 0.5))  # Adjusted for negative values

        # Convert components
        x = float_to_snorm10(normal.x)
        y = float_to_snorm10(normal.y)
        z = float_to_snorm10(normal.z)

        # Pack maintaining GLM format
        packed = x | (y << 10) | (z << 20)

        return struct.pack('<I', packed)

    # --------------------------------------------------------
    # Pack Tangent
    # --------------------------------------------------------
    @staticmethod
    def pack_tangent(tangent):
        """
        Converts a tangent into the 10-10-10-2 compression format.
        
        Args:
            tangent: mathutils.Vector of the tangent
            
        Returns:
            bytes: Compressed tangent in binary format (4 bytes)
        """

        def float_to_snorm10(f):
            f = max(-1.0, min(1.0, f))
            if f >= 0:
                return int(f * 511.0 + 0.5)
            else:
                return int(1024 + (f * 511.0 - 0.5))

        x = float_to_snorm10(tangent.x)
        y = float_to_snorm10(tangent.y)
        z = float_to_snorm10(tangent.z)
        w = 0  # Handedness

        packed_int = x | (y << 10) | (z << 20) | (w << 30)
        return struct.pack('I', packed_int)  # 4 byte little-endian unsigned int

    # --------------------------------------------------------
    # Pack UV Coordinates
    # --------------------------------------------------------
    @staticmethod
    def pack_uv(uv):
        """
        Packs UV coordinates in compressed format.

        Args:
            uv (mathutils.Vector): UV coordinates to pack

        Returns:
            bytes: UV coordinates packed
        """
        # Validate and correct UV coordinates
        uv.x = max(0.0, min(1.0, uv.x))
        uv.y = max(0.0, min(1.0, uv.y))

        # Convert to half-float (16-bit)
        u_half = struct.unpack('<H', struct.pack('<e', uv.x))[0]
        v_half = struct.unpack('<H', struct.pack('<e', uv.y))[0]

        # Pack in a single uint32
        packed = (v_half << 16) | u_half
        return struct.pack('<I', packed)


    # --------------------------------------------------------
    # Write Chunk Header
    # --------------------------------------------------------
    @staticmethod
    def write_chunk_header(file, chunk_id, chunk_size):
        """
        Writes a chunk header to the OVO file.

        Args:
            file (file): Output file
            chunk_id (int): Chunk type ID
            chunk_size (int): Chunk size in bytes
        """
        # Map chunk IDs to readable names for debug
        chunk_names = {
            0: "OBJECT",
            1: "NODE",
            9: "MATERIAL",
            16: "LIGHT",
            18: "MESH"
        }

        chunk_name = chunk_names.get(chunk_id, f"TYPE_{chunk_id}")
        log(f"[OVOPacker] Writing chunk: {chunk_name} (ID={chunk_id}, Size={chunk_size} bytes)", category="", indent=1)

        file.write(struct.pack('2I', chunk_id, chunk_size))

        # --------------------------------------------------------
    # Debug Chunk Content
    # --------------------------------------------------------
    def debug_chunk_content(self, chunk_type, content_dict):
        """
        Prints a debug summary of chunk content.

        Args:
            chunk_type (str): Type of chunk (e.g. "NODE", "MESH")
            content_dict (dict): Dictionary with key content values
        """
        print(f"    [OVOPacker] {chunk_type} content summary:")
        for key, value in content_dict.items():
            if isinstance(value, (mathutils.Vector, mathutils.Matrix)):
                log(f"{key}: {type(value).__name__}", category="", indent=2)
            elif isinstance(value, (list, tuple)) and len(value) > 4:
                log(f"{key}: {type(value).__name__} [{len(value)} items]", category="", indent=2)
            else:
                log(f"{key}: {value}", category="", indent=2)