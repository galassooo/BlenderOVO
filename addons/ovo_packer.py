import math
import struct
import mathutils


class OVOPacker:
    """
    Class that handles data packing operations for the OVO format.
    Separates data serialization logic from export logic.
    """

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
        # No print statement here as this is called very frequently
        return packed

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

    @staticmethod
    def pack_tangent(tangent):
        """
        Converte e comprime una tangente in un unsigned int.
        
        Args:
            tangent: mathutils.Vector della tangente
            
        Returns:
            int: Valore compresso
        """
        # Converti nel sistema di coordinate OpenGL (x, z, -y)
        t = mathutils.Vector((tangent.x, tangent.z, -tangent.y)).normalized()
        
        # Mappiamo da [-1,1] a [0,1023] per ogni componente
        def float_to_int10(f):
            f = max(-1.0, min(1.0, f))
            if f >= 0:
                return int(f * 511)
            else:
                return int(1024 + f * 511)
        
        x = float_to_int10(t.x)
        y = float_to_int10(t.y)
        z = float_to_int10(t.z)
        w = 0  # Handedness
        
        # Pacchetta in un unico valore
        packed = x | (y << 10) | (z << 20) | (w << 30)
        
        return packed
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
        print(f"    [OVOPacker] Writing chunk: {chunk_name} (ID={chunk_id}, size={chunk_size} bytes)")

        file.write(struct.pack('2I', chunk_id, chunk_size))

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
                print(f"      - {key}: {type(value).__name__}")
            elif isinstance(value, (list, tuple)) and len(value) > 4:
                print(f"      - {key}: {type(value).__name__}[{len(value)} items]")
            else:
                print(f"      - {key}: {value}")