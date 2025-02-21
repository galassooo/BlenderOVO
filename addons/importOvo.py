import bpy
import struct
import mathutils
import io
import os
from bpy_extras.io_utils import ImportHelper
from bpy.types import Operator
from bpy.props import StringProperty

# ===================================
#   Blender Addon Information
# ===================================
bl_info = {
    "name": "OVO Format Importer",
    "author": "Your Name",
    "version": (1, 0),
    "blender": (4, 0, 0),
    "location": "File > Import > OverView Object (.ovo)",
    "description": "Import an OVO scene file into Blender with correct hierarchy",
    "category": "Import-Export",
}

# ====================================
#   OVO File Reader
# ====================================
class OVOChunk:
    """
    @class OVOChunk
    @brief Represents a single chunk in an OVO file, including ID, size, and data.
    """
    def __init__(self, chunk_id, chunk_size, data):
        self.chunk_id = chunk_id  # Chunk type identifier
        self.chunk_size = chunk_size  # Size of the chunk data
        self.data = data  # Raw binary data of the chunk

    @staticmethod
    def read_chunk(file):
        """
        @brief Reads the next chunk from the binary OVO file.
        @param file The binary file object.
        @return An OVOChunk object if successful, None if EOF is reached.
        """
        header = file.read(8)  # Read the chunk ID (4 bytes) and size (4 bytes)
        if len(header) < 8:
            return None  # End of file reached

        chunk_id, chunk_size = struct.unpack("<II", header)  # Read ID and size (little-endian)
        data = file.read(chunk_size)  # Read chunk data
        return OVOChunk(chunk_id, chunk_size, data)

# ====================================
#   OVO Importer
# ====================================
class OVOImporter:
    """
    @class OVOImporter
    @brief Handles reading and parsing of OVO files.
    """
    def __init__(self, filepath):
        self.filepath = filepath
        self.chunks = []
        self.materials = {}
        self.texture_directory = os.path.dirname(filepath)

    def read_ovo_file(self):
        """
        @brief Reads the entire OVO file and stores chunks.
        """
        with open(self.filepath, "rb") as file:
            while True:
                chunk = OVOChunk.read_chunk(file)
                if chunk is None:
                    break
                self.chunks.append(chunk)

        print(f"Successfully read {len(self.chunks)} chunks from {self.filepath}")
        return True

    def import_scene(self):
        """
        @brief Initiates the import process.
        """
        if not self.read_ovo_file():
            return {'CANCELLED'}

        scene = OVOScene()

        # First, load materials
        for chunk in self.chunks:
            if chunk.chunk_id == 9:  # MATERIAL CHUNK
                material = OVOMaterial.parse_material(chunk.data)
                material.blender_material = material.create_blender_material(self.texture_directory)
                self.materials[material.name] = material  # Store the OVOMaterial instance

        # Process scene hierarchy
        for chunk in self.chunks:
            if chunk.chunk_id == 1:  # NODE CHUNK
                node = scene.parse_scene(chunk.data)

        # Process lights
        for chunk in self.chunks:
            if chunk.chunk_id == 16:  # LIGHT CHUNK
                light = OVOLight.parse_light(chunk.data)
                light.create_blender_light()

        # Process meshes
        for chunk in self.chunks:
            if chunk.chunk_id == 18:  # MESH CHUNK
                mesh = OVOMesh.parse_mesh(chunk.data)
                mesh_obj = mesh.create_blender_mesh()

                # Assign material if available
                if mesh.material in self.materials:
                    material = self.materials[mesh.material]  # Get OVOMaterial instance
                    if material.blender_material:
                        material.apply_to_mesh(mesh_obj)

        return {'FINISHED'}

# ====================================
#  Blender Import Operator
# ====================================
class OT_ImportOVO(Operator, ImportHelper):
    """
    @class OT_ImportOVO
    @brief Blender operator to handle OVO file import.
    """
    bl_idname = "import_scene.ovo"
    bl_label = "Import OVO"
    filename_ext = ".ovo"

    filter_glob: StringProperty(default="*.ovo", options={'HIDDEN'})

    def execute(self, context):
        importer = OVOImporter(self.filepath)
        return importer.import_scene()


# ====================================
#  Blender Registration Functions
# ====================================
def menu_func_import(self, context):
    self.layout.operator(OT_ImportOVO.bl_idname, text="OverVision Object (.ovo)")


def register():
    bpy.utils.register_class(OT_ImportOVO)
    bpy.types.TOPBAR_MT_file_import.append(menu_func_import)


def unregister():
    bpy.utils.unregister_class(OT_ImportOVO)
    bpy.types.TOPBAR_MT_file_import.remove(menu_func_import)


# Run this script in Blender to register the add-on
if __name__ == "__main__":
    register()

# ====================================
#  OVO Object Hierarchy
# ====================================
class OVOObject:
    """
    @class OVOObject
    @brief Base class for all OVO objects in the scene hierarchy.
    """
    def __init__(self, name, matrix):
        self.name = name
        self.matrix = matrix  # 4x4 transformation matrix
        self.children = []

    def add_child(self, child):
        """
        @brief Adds a child node to this object.
        @param child The child node to be added.
        """
        self.children.append(child)


class OVONode(OVOObject):
    """
    @class OVONode
    @brief Represents a generic node in the OVO scenegraph.
    """
    def __init__(self, name, matrix):
        super().__init__(name, matrix)

# ====================================
#  OVO Mesh Class
# ====================================
class OVOMesh(OVONode):
    """
    @class OVOMesh
    @brief Represents a 3D mesh node in the OVO scene.
    """
    def __init__(self, name, matrix, material, vertices, normals, uvs, faces):
        super().__init__(name, matrix)
        self.material = material
        self.vertices = vertices
        self.normals = normals
        self.uvs = uvs
        self.faces = faces

    @staticmethod
    def parse_mesh(chunk_data):
        position = 0
        file = io.BytesIO(chunk_data)  # Convert chunk_data to a file-like object

        # Read mesh name
        mesh_name = OVOScene._read_string(file)
        print(f"\nProcessing MESH: {mesh_name}")

        # Read transformation matrix (16 floats)
        matrix_values = struct.unpack('16f', file.read(64))
        transformation_matrix = mathutils.Matrix([matrix_values[i:i + 4] for i in range(0, 16, 4)])
        print(f"Transformation Matrix:\n{transformation_matrix}")

        # Read number of children
        num_children = struct.unpack('I', file.read(4))[0]
        print(f"Number of children: {num_children}")

        # Read target node (unused, usually "[none]")
        target_node = OVOScene._read_string(file)

        # Read mesh subtype
        mesh_subtype = struct.unpack('B', file.read(1))[0]
        print(f"Mesh Subtype: {mesh_subtype}")

        # Read material name
        material_name = OVOScene._read_string(file)
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

        return OVOMesh(mesh_name, transformation_matrix, material_name, vertices, normals, uvs, faces)

    @staticmethod
    def _unpack_normal(packed_normal):
        """
        @brief Unpacks a normal stored in GL_INT_10_10_10_2_REV format.
        @param packed_normal The packed integer normal.
        @return A normalized (x, y, z) tuple.
        """
        x = ((packed_normal >> 0) & 0x3FF) / 511.5 - 1.0
        y = ((packed_normal >> 10) & 0x3FF) / 511.5 - 1.0
        z = ((packed_normal >> 20) & 0x3FF) / 511.5 - 1.0
        return (x, y, z)

    @staticmethod
    def _unpack_half_float(data):
        """
        @brief Converts a 16-bit half-float to a 32-bit float UV coordinate.
        @param data The binary data containing the half-float.
        @return A (u, v) tuple.
        """
        u, v = struct.unpack("<e e", data)  # "<e" = little-endian half-float
        return (u, v)

    def create_blender_mesh(self):
        """
        @brief Creates a Blender mesh object from this OVOMesh.
        """
        if len(self.faces) == 0:
            print(f"Warning: Mesh {self.name} has no faces and may not be visible.")

        mesh_data = bpy.data.meshes.new(self.name)

        # Check if faces exist before creating mesh
        if len(self.vertices) > 0 and len(self.faces) > 0:
            mesh_data.from_pydata(self.vertices, [], self.faces)
        else:
            print(f"Error: Mesh {self.name} has no valid faces.")

        # Assign normals
        mesh_data.create_normals_split()
        for i, loop in enumerate(mesh_data.loops):
            loop.normal = self.normals[loop.vertex_index]
        mesh_data.validate()
        mesh_data.update()

        # Assign UVs
        uv_layer = mesh_data.uv_layers.new()
        for i, loop in enumerate(mesh_data.loops):
            uv_layer.data[i].uv = self.uvs[loop.vertex_index]

        obj = bpy.data.objects.new(self.name, mesh_data)
        obj.matrix_world = self.matrix
        bpy.context.collection.objects.link(obj)

        print(
            f"Blender Mesh Created: {self.name}, Vertices: {len(self.vertices)}, Faces: {len(self.faces)}")  # Debugging info

        self.blender_object = obj
        return obj

# ====================================
#  OVO Material Class
# ====================================
class OVOMaterial:
    """
    @class OVOMaterial
    @brief Represents a material in the OVO format.
    """
    def __init__(self, name, base_color, roughness, metallic, transparency, emissive, textures):
        self.name = name
        self.base_color = base_color
        self.roughness = roughness
        self.metallic = metallic
        self.transparency = transparency
        self.emissive = emissive
        self.textures = textures
        self.blender_material = None  # Stores the Blender material reference

    @staticmethod
    def parse_material(chunk_data):
        """
        Parses an OVO material chunk.
        """
        file = io.BytesIO(chunk_data)  # Convert binary data to a file-like object

        # Read material name
        name = OVOScene._read_string(file)

        # Read emissive color (3 floats)
        emissive = struct.unpack("<3f", file.read(12))

        # Read base (albedo) color (3 floats)
        base_color = struct.unpack("<3f", file.read(12))

        # Read roughness (1 float)
        roughness = struct.unpack("<f", file.read(4))[0]

        # Read metalness (1 float)
        metallic = struct.unpack("<f", file.read(4))[0]

        # Read transparency (1 float)
        transparency = struct.unpack("<f", file.read(4))[0]

        # Read texture file names
        textures = {}
        texture_types = ["albedo", "normal", "height", "roughness", "metalness"]

        for texture_type in texture_types:
            texture_name = OVOScene._read_string(file)
            textures[texture_type] = texture_name if texture_name != "[none]" else None

        return OVOMaterial(name, base_color, roughness, metallic, transparency, emissive, textures)

    def create_blender_material(self, texture_directory):
        """
        @brief Creates a Blender material from this OVOMaterial and loads textures.
        @param texture_directory The directory where textures are stored.
        """
        mat = bpy.data.materials.new(name=self.name)
        mat.use_nodes = True

        # Find the "Principled BSDF" node
        bsdf = None
        for node in mat.node_tree.nodes:
            if node.type == 'BSDF_PRINCIPLED':
                bsdf = node
                break

        if bsdf is None:
            print(f"Error: Principled BSDF node not found in material {self.name}")
            return mat  # Return the material without modifications

        # Assign base color
        if "Base Color" in bsdf.inputs:
            bsdf.inputs["Base Color"].default_value = (*self.base_color, 1.0)

        # Assign roughness and metallic
        if "Roughness" in bsdf.inputs:
            bsdf.inputs["Roughness"].default_value = self.roughness
        if "Metallic" in bsdf.inputs:
            bsdf.inputs["Metallic"].default_value = self.metallic

        # Assign transparency (Alpha)
        if "Alpha" in bsdf.inputs and self.transparency < 1.0:
            mat.blend_method = 'BLEND'
            mat.shadow_method = 'HASHED'
            bsdf.inputs["Alpha"].default_value = self.transparency

        # Assign emissive color
        if "Emission" in bsdf.inputs:
            bsdf.inputs["Emission"].default_value = (*self.emissive, 1.0)

        self.blender_material = mat
        return mat

    def _add_texture(self, material, bsdf, texture_path, texture_type):
        """
        @brief Adds a texture map to the Blender material.
        @param material The Blender material.
        @param bsdf The Principled BSDF node.
        @param texture_path Path to the texture file.
        @param texture_type The type of texture (albedo, normal, etc.).
        """
        # Create texture node
        nodes = material.node_tree.nodes
        links = material.node_tree.links

        tex_image = nodes.new(type="ShaderNodeTexImage")
        tex_image.image = bpy.data.images.load(texture_path)
        tex_image.label = texture_type.capitalize()

        # Connect to the correct slot
        texture_slots = {
            "albedo": "Base Color",
            "normal": "Normal",
            "height": "Displacement",
            "roughness": "Roughness",
            "metalness": "Metallic"
        }

        if texture_type in texture_slots:
            if texture_type == "normal":
                # Special case: Normal map requires a normal map node
                normal_map = nodes.new(type="ShaderNodeNormalMap")
                links.new(tex_image.outputs["Color"], normal_map.inputs["Color"])
                links.new(normal_map.outputs["Normal"], bsdf.inputs["Normal"])
            else:
                links.new(tex_image.outputs["Color"], bsdf.inputs[texture_slots[texture_type]])

    def apply_to_mesh(self, mesh_obj):
        """
        @brief Applies this material to a given Blender mesh object.
        @param mesh_obj The Blender mesh object.
        """
        if not self.blender_material:
            print(f"Warning: No Blender material found for {self.name}")
            return

        if not mesh_obj.data.materials:
            mesh_obj.data.materials.append(self.blender_material)
        else:
            mesh_obj.data.materials[0] = self.blender_material

# ====================================
#  OVO Light Class
# ====================================
class OVOLight(OVONode):
    """
    @class OVOLight
    @brief Represents a light source in the OVO scene.
    """
    def __init__(self, name, matrix, light_type, color, radius, direction, cutoff, spot_exponent, shadow, volumetric):
        super().__init__(name, matrix)
        self.light_type = light_type
        self.color = color
        self.radius = radius
        self.direction = direction
        self.cutoff = cutoff
        self.spot_exponent = spot_exponent
        self.shadow = shadow
        self.volumetric = volumetric

    @staticmethod
    def parse_light(chunk_data):
        """
        Parses an OVO light chunk.
        """
        file = io.BytesIO(chunk_data)  # Convert binary data to file-like object

        # Read node name
        name = OVOScene._read_string(file)

        # Read 4x4 transformation matrix
        matrix_values = struct.unpack("<16f", file.read(64))
        matrix = mathutils.Matrix([matrix_values[i:i + 4] for i in range(0, 16, 4)])

        # Read number of child nodes
        num_children = struct.unpack("<I", file.read(4))[0]

        # Read target node name
        target_name = OVOScene._read_string(file)

        # Read light subtype (1 byte)
        light_type = struct.unpack("<B", file.read(1))[0]

        # Read light color (3 floats)
        color = struct.unpack("<3f", file.read(12))

        # Read light radius (1 float)
        radius = struct.unpack("<f", file.read(4))[0]

        # Read light direction (3 floats)
        direction = struct.unpack("<3f", file.read(12))

        # Read cutoff angle (1 float)
        cutoff = struct.unpack("<f", file.read(4))[0]

        # Read spot exponent (1 float)
        spot_exponent = struct.unpack("<f", file.read(4))[0]

        # Read shadow flag (1 byte)
        shadow = struct.unpack("<B", file.read(1))[0]

        # Read volumetric flag (1 byte)
        volumetric = struct.unpack("<B", file.read(1))[0]

        return OVOLight(name, matrix, light_type, color, radius, direction, cutoff, spot_exponent, shadow, volumetric)

    def create_blender_light(self):
        """
        @brief Creates a Blender light from this OVOLight.
        """
        # Map OVO light type to Blender light type
        light_types = {0: 'POINT', 1: 'SUN', 2: 'SPOT'}
        light_data = bpy.data.lights.new(name=self.name, type=light_types.get(self.light_type, 'POINT'))
        light_obj = bpy.data.objects.new(self.name, light_data)

        # Assign properties
        light_data.color = self.color
        light_data.energy = self.radius * 10  # Scale intensity based on radius

        # Spot light settings
        if self.light_type == 2:  # Spot
            light_data.spot_size = self.cutoff
            light_data.spot_blend = self.spot_exponent / 10.0

        # Enable shadows if needed
        light_data.use_shadow = bool(self.shadow)

        # Apply transformation matrix (convert from OpenGL to Blender)
        light_obj.matrix_world = self.matrix

        bpy.context.collection.objects.link(light_obj)

        self.blender_object = light_obj
        return light_obj

# ====================================
#  OVO Scene Class
# ====================================
class OVOScene:
    """
    @class OVOScene
    @brief Manages the parsing and reconstruction of the OVO scene hierarchy.
    """
    def __init__(self):
        self.root = None

    def parse_scene(self, chunk_data):
        """
        Parses an OVO node chunk and reconstructs the hierarchy.
        """
        file = io.BytesIO(chunk_data)  # Convert binary data to a file-like object

        # Read node name
        name = self._read_string(file)

        # Read transformation matrix (16 floats)
        if file.tell() + 64 > len(chunk_data):
            print(f"Error: Not enough data for transformation matrix at position {file.tell()}.")
            return None
        matrix_values = struct.unpack("<16f", file.read(64))
        matrix = mathutils.Matrix([matrix_values[i:i + 4] for i in range(0, 16, 4)])

        # Read number of child nodes
        if file.tell() + 4 > len(chunk_data):
            print(f"Error: Not enough data for child node count at position {file.tell()}.")
            return None
        num_children = struct.unpack("<I", file.read(4))[0]

        # Read target node name
        target_name = self._read_string(file)

        # Convert OpenGL matrix (row-major, Y-up) to Blender (column-major, Z-up)
        matrix = self._convert_matrix(matrix)

        # Create the root node
        node = OVONode(name, matrix)

        # Recursively process children
        for _ in range(num_children):
            if file.tell() >= len(chunk_data):
                print(f"Error: Not enough data for child node at position {file.tell()}. Skipping remaining nodes.")
                break
            child = self.parse_scene(chunk_data[file.tell():])
            if child:
                node.add_child(child)

        return node

    @staticmethod
    def _read_string(file):
        """Reads a null-terminated string from the binary file."""
        chars = []
        while True:
            char = file.read(1)
            if char == b'\x00' or not char:
                break
            chars.append(char)
        return b''.join(chars).decode('utf-8', errors='replace')

    def _convert_matrix(self, matrix):
        """
        @brief Converts an OpenGL matrix (row-major, Y-up) to Blender (column-major, Z-up).
        @param matrix The original 4x4 matrix.
        @return The converted Blender-compatible matrix.
        """
        # OpenGL uses row-major order, Blender uses column-major
        matrix.transpose()

        # Convert Y-up (OpenGL) to Z-up (Blender)
        conversion_matrix = mathutils.Matrix([
            [1,  0,  0,  0],
            [0,  0,  1,  0],
            [0, -1,  0,  0],
            [0,  0,  0,  1]
        ])
        return conversion_matrix @ matrix  # Apply the transformation

"""""
if __name__ == "__main__":
    # Set the test file path
    filepath = "C:\\Users\\kevin\\Desktop\\SemesterProject\\addons\\bin\\output.ovo"

    # Ensure the file exists before importing
    if not os.path.exists(filepath):
        print(f"Error: OVO file '{filepath}' not found.")
    else:
        print(f"Loading OVO file: {filepath}")

        # Run the importer
        importer = OVOImporter(filepath)
        result = importer.import_scene()

        # Force update of the Blender scene
        bpy.context.view_layer.update()
        print("Scene update complete.")

        # Debugging: Print all objects in the scene
        print("Imported objects:")
        for obj in bpy.data.objects:
            print(f"- {obj.name}: {obj.type}, Location: {obj.location}")

        print("Debugging Complete.")
"""