import bpy
import struct
import os
import mathutils
from bpy_extras.io_utils import ImportHelper
from bpy.types import Operator
from bpy.props import StringProperty


bl_info = {
    "name": "OVO Format Importer",
    "author": "Martina Galasso & Kevin Quarenghi",
    "version": (0, 1),
    "blender": (4, 2, 1),
    "location": "File > Import > OverView Object (.ovo)",
    "description": "Import an OVO scene file into Blender",
    "category": "Import-Export",
}


class ChunkType:
    """
    Defines the chunk type constants from the OVO format.
    These should match the IDs found in the OVO documentation.
    """
    OBJECT = 0
    NODE = 1
    OBJECT2D = 2
    OBJECT3D = 3
    LIST = 4
    BUFFER = 5
    SHADER = 6
    TEXTURE = 7
    FILTER = 8
    MATERIAL = 9
    FBO = 10
    QUAD = 11
    BOX = 12
    SKYBOX = 13
    FONT = 14
    CAMERA = 15
    LIGHT = 16
    BONE = 17
    MESH = 18
    SKINNED = 19
    INSTANCED = 20
    PIPELINE = 21
    EMITTER = 22
    ANIM = 23
    PHYSICS = 24
    LAST = 25

    @staticmethod
    def get_chunk_name(chunk_id):
        """Returns the name of the chunk type given its ID."""
        chunk_map = {value: key for key, value in ChunkType.__dict__.items() if isinstance(value, int)}
        return chunk_map.get(chunk_id, f"UNKNOWN ({chunk_id})")

class OVO_Importer:
    """
    A class to import OVO files into Blender by reading and parsing binary chunks.

    Attributes:
        filepath (str): The path to the OVO file being imported.
    """

    def __init__(self, filepath):
        """
        Initializes the OVO importer.

        Args:
            filepath (str): The path to the OVO file.
        """
        self.filepath = filepath
        self.chunks = []  # Initialize this list to store parsed chunks
        self.meshes = []  # Also initialize meshes to store parsed meshes
        self.materials = {}  # Dictionary to store materials
        self.nodes = []  # Stores parsed nodes
        self.lights = []  # Stores parsed lights
        self.object_data = {}  # Stores scene-level metadata

    def read_string(self, file):
        """
        Reads a null-terminated string from the OVO file.

        Args:
            file (file object): The opened binary file.

        Returns:
            str: The decoded string.
        """
        chars = []
        while True:
            char = file.read(1)
            if char == b'\0' or not char:
                break
            chars.append(char)
        return b''.join(chars).decode('utf-8')

    def parse_mesh_chunk(self, file, chunk_size):
        """
        Reads and processes a MESH chunk from the OVO file.

        Args:
            file (file object): The opened binary file.
            chunk_size (int): The size of the chunk to read.
        """
        start_position = file.tell()

        # Read mesh name
        mesh_name = self.read_string(file)
        print(f"\nProcessing MESH: {mesh_name}")

        # Read transformation matrix (16 floats)
        matrix_values = struct.unpack('16f', file.read(64))
        transformation_matrix = mathutils.Matrix([matrix_values[i:i + 4] for i in range(0, 16, 4)])
        print(f"Transformation Matrix:\n{transformation_matrix}")

        # Read number of children
        num_children = struct.unpack('I', file.read(4))[0]
        print(f"Number of children: {num_children}")

        # Read target node (unused, usually "[none]")
        target_node = self.read_string(file)

        # Read mesh subtype
        mesh_subtype = struct.unpack('B', file.read(1))[0]
        print(f"Mesh Subtype: {mesh_subtype}")

        # Read material name
        material_name = self.read_string(file)
        print(f"Material: {material_name}")

        # Read bounding box data
        radius = struct.unpack('f', file.read(4))[0]
        min_box = struct.unpack('3f', file.read(12))
        max_box = struct.unpack('3f', file.read(12))
        print(f"Bounding Box Min: {min_box}, Max: {max_box}, Radius: {radius}")

        # Read physics flag
        physics_flag = struct.unpack('B', file.read(1))[0]
        print(f"Physics Flag: {physics_flag}")

        # Read LOD count (always 1 in most cases)
        lod_count = struct.unpack('I', file.read(4))[0]
        print(f"Number of LODs: {lod_count}")

        # Read vertex and face counts
        vertex_count, face_count = struct.unpack('2I', file.read(8))
        print(f"Vertices: {vertex_count}, Faces: {face_count}")

        vertices = []
        normals = []
        uvs = []
        faces = []

        # Read vertex data
        for _ in range(vertex_count):
            pos = struct.unpack('3f', file.read(12))  # Position
            normal_data = struct.unpack('I', file.read(4))[0]  # Packed Normal
            uv_data = struct.unpack('I', file.read(4))[0]  # Packed UVs
            tangent = struct.unpack('I', file.read(4))[0]  # Placeholder for tangent (not used yet)

            # Unpacking normal
            nx = ((normal_data & 0x3FF) / 511.0) * 2.0 - 1.0
            ny = (((normal_data >> 10) & 0x3FF) / 511.0) * 2.0 - 1.0
            nz = (((normal_data >> 20) & 0x3FF) / 511.0) * 2.0 - 1.0
            normal = (nx, ny, nz)

            # Unpacking UVs
            u = ((uv_data & 0xFFFF) / 65535.0)
            v = (((uv_data >> 16) & 0xFFFF) / 65535.0)
            uv = (u, v)

            vertices.append(pos)
            normals.append(normal)
            uvs.append(uv)

        print(f"Read {len(vertices)} vertices.")

        # Read faces (indices)
        for _ in range(face_count):
            face = struct.unpack('3I', file.read(12))
            faces.append(face)

        print(f"Read {len(faces)} faces.")

        # Store parsed mesh
        self.meshes.append({
            "name": mesh_name,
            "material": material_name,
            "vertices": vertices,
            "normals": normals,
            "uvs": uvs,
            "faces": faces,
            "matrix": transformation_matrix
        })

        # Ensure we fully read the chunk
        end_position = file.tell()
        remaining_bytes = chunk_size - (end_position - start_position)
        if remaining_bytes > 0:
            file.read(remaining_bytes)  # Skip padding if needed

    def parse_material_chunk(self, file, chunk_size):
        """
        Reads and processes a MATERIAL chunk from the OVO file.

        Args:
            file (file object): The opened binary file.
            chunk_size (int): The size of the chunk to read.
        """
        start_position = file.tell()

        # Read material name
        material_name = self.read_string(file)
        print(f"\nProcessing MATERIAL: {material_name}")

        # Read emission color (3 floats)
        emission_color = struct.unpack('3f', file.read(12))

        # Read base color (3 floats)
        base_color = struct.unpack('3f', file.read(12))

        # Read roughness, metallic, alpha (3 floats)
        roughness, metallic, alpha = struct.unpack('3f', file.read(12))

        # Read texture file paths (5 strings)
        albedo_texture = self.read_string(file)
        normal_texture = self.read_string(file)
        height_texture = self.read_string(file)
        roughness_texture = self.read_string(file)
        metallic_texture = self.read_string(file)

        print(f"  Emission Color: {emission_color}")
        print(f"  Base Color: {base_color}, Roughness: {roughness}, Metallic: {metallic}, Alpha: {alpha}")
        print(
            f"  Textures -> Albedo: {albedo_texture}, Normal: {normal_texture}, Height: {height_texture}, Roughness: {roughness_texture}, Metallic: {metallic_texture}")

        # Store parsed material
        self.materials[material_name] = {
            "emission": emission_color,
            "base_color": base_color,
            "roughness": roughness,
            "metallic": metallic,
            "alpha": alpha,
            "textures": {
                "albedo": albedo_texture,
                "normal": normal_texture,
                "height": height_texture,
                "roughness": roughness_texture,
                "metallic": metallic_texture,
            }
        }

        # Ensure we fully read the chunk
        end_position = file.tell()
        remaining_bytes = chunk_size - (end_position - start_position)
        if remaining_bytes > 0:
            file.read(remaining_bytes)  # Skip padding if needed

    def parse_node_chunk(self, file, chunk_size):
        """
        Reads and processes a NODE chunk from the OVO file.

        Args:
            file (file object): The opened binary file.
            chunk_size (int): The size of the chunk to read.
        """
        start_position = file.tell()

        # Read node name
        node_name = self.read_string(file)
        print(f"\nProcessing NODE: {node_name}")

        # Read transformation matrix (16 floats)
        matrix_values = struct.unpack('16f', file.read(64))
        transformation_matrix = mathutils.Matrix([matrix_values[i:i + 4] for i in range(0, 16, 4)])
        print(f"Transformation Matrix:\n{transformation_matrix}")

        # Read number of children
        num_children = struct.unpack('I', file.read(4))[0]
        print(f"Number of Children: {num_children}")

        # Read target node (if any)
        target_node = self.read_string(file)
        print(f"Target Node: {target_node}")

        # Store parsed node
        self.nodes.append({
            "name": node_name,
            "matrix": transformation_matrix,
            "children": num_children,
            "target": target_node
        })

        # Ensure we fully read the chunk
        end_position = file.tell()
        remaining_bytes = chunk_size - (end_position - start_position)
        if remaining_bytes > 0:
            file.read(remaining_bytes)  # Skip padding if needed

    def parse_light_chunk(self, file, chunk_size):
        """
        Reads and processes a LIGHT chunk from the OVO file.

        Args:
            file (file object): The opened binary file.
            chunk_size (int): The size of the chunk to read.
        """
        start_position = file.tell()

        # Read light name
        light_name = self.read_string(file)
        print(f"\nProcessing LIGHT: {light_name}")

        # Read transformation matrix (16 floats)
        matrix_values = struct.unpack('16f', file.read(64))
        transformation_matrix = mathutils.Matrix([matrix_values[i:i + 4] for i in range(0, 16, 4)])
        print(f"Transformation Matrix:\n{transformation_matrix}")

        # Read number of children
        num_children = struct.unpack('I', file.read(4))[0]
        print(f"Number of Children: {num_children}")

        # Read target node
        target_node = self.read_string(file)

        # Read light subtype (0 = Omni, 1 = Directional, 2 = Spot)
        light_type = struct.unpack('B', file.read(1))[0]
        print(f"Light Type: {light_type}")

        # Read light color (3 floats)
        color = struct.unpack('3f', file.read(12))
        print(f"Light Color: {color}")

        # Read radius
        radius = struct.unpack('f', file.read(4))[0]
        print(f"Light Radius: {radius}")

        # Read direction (only for directional or spot lights)
        direction = struct.unpack('3f', file.read(12))
        print(f"Light Direction: {direction}")

        # Read cutoff angle (for spot lights)
        cutoff_angle = struct.unpack('f', file.read(4))[0]
        print(f"Cutoff Angle: {cutoff_angle}")

        # Read spot exponent
        spot_exponent = struct.unpack('f', file.read(4))[0]
        print(f"Spot Exponent: {spot_exponent}")

        # Read shadow flag (0 = No Shadows, 1 = Shadows)
        cast_shadows = struct.unpack('B', file.read(1))[0]
        print(f"Casts Shadows: {cast_shadows}")

        # Read volumetric flag (0 = No Volumetric Light, 1 = Yes)
        volumetric = struct.unpack('B', file.read(1))[0]
        print(f"Volumetric: {volumetric}")

        # Store parsed light
        self.lights.append({
            "name": light_name,
            "matrix": transformation_matrix,
            "type": light_type,
            "color": color,
            "radius": radius,
            "direction": direction,
            "cutoff": cutoff_angle,
            "spot_exponent": spot_exponent,
            "shadows": cast_shadows,
            "volumetric": volumetric
        })

        # Ensure we fully read the chunk
        end_position = file.tell()
        remaining_bytes = chunk_size - (end_position - start_position)
        if remaining_bytes > 0:
            file.read(remaining_bytes)  # Skip padding if needed

    def parse_object_chunk(self, file, chunk_size):
        """
        Reads and processes an OBJECT chunk from the OVO file.

        Args:
            file (file object): The opened binary file.
            chunk_size (int): The size of the chunk to read.
        """
        start_position = file.tell()

        # Read the OVO version number (4 bytes)
        ovo_version = struct.unpack('I', file.read(4))[0]
        print(f"\nProcessing OBJECT chunk... OVO Version: {ovo_version}")

        # Store parsed object metadata
        self.object_data = {"version": ovo_version}

        # Ensure we fully read the chunk
        end_position = file.tell()
        remaining_bytes = chunk_size - (end_position - start_position)
        if remaining_bytes > 0:
            file.read(remaining_bytes)  # Skip padding if needed

    def parse_file(self):
        """
        Reads the OVO file structure and processes each chunk based on its type.
        """
        try:
            with open(self.filepath, 'rb') as file:
                print(f"Opening OVO file: {self.filepath}")

                while True:
                    chunk_header = file.read(8)  # Read 2 Integers (Chunk ID + Size)
                    if not chunk_header:
                        break  # End of file

                    chunk_id, chunk_size = struct.unpack('2I', chunk_header)
                    print(
                        f"Found chunk ID: {chunk_id} ({ChunkType.get_chunk_name(chunk_id)}), Size: {chunk_size} bytes")

                    chunk_start = file.tell()  # Save position for reading content

                    # Process based on chunk type
                    if chunk_id == ChunkType.OBJECT:
                        print("Processing OBJECT chunk...")
                        self.parse_object_chunk(file, chunk_size)

                    elif chunk_id == ChunkType.NODE:
                        print("Processing NODE chunk...")
                        self.parse_node_chunk(file, chunk_size)

                    elif chunk_id == ChunkType.MATERIAL:
                        print("Processing MATERIAL chunk...")
                        self.parse_material_chunk(file, chunk_size)

                    elif chunk_id == ChunkType.MESH:
                        print("Processing MESH chunk...")
                        self.parse_mesh_chunk(file, chunk_size)

                    elif chunk_id == ChunkType.LIGHT:
                        print("Processing LIGHT chunk...")
                        self.parse_light_chunk(file, chunk_size)

                    else:
                        print(f"Skipping unknown chunk ID: {chunk_id}")

                    # Ensure we fully read the chunk
                    file.seek(chunk_start + chunk_size, os.SEEK_SET)

            print("Finished reading OVO file.")

        except FileNotFoundError:
            print(f"Error: File '{self.filepath}' not found.")
        except Exception as e:
            print(f"Error while parsing file: {e}")


# Example usage
if __name__ == "__main__":
    filepath = "C:\\Users\\kevin\\Desktop\\SemesterProject\\addons\\bin\\output.ovo"
    importer = OVO_Importer(filepath)
    importer.parse_file()