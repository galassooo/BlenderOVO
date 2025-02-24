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
    "location": "File > Import > OverVision Object (.ovo)",
    "description": "Import an OVO scene file into Blender",
    "category": "Import-Export",
}

# ====================================
#   OVO File Reader
# ====================================
class OVOChunk:
    """
    Represents a single chunk in an OVO file.
    """
    def __init__(self, chunk_id, chunk_size, data):
        self.chunk_id = chunk_id  # Chunk type identifier
        self.chunk_size = chunk_size  # Size of the chunk data
        self.data = data  # Raw binary data

    @staticmethod
    def read_chunk(file):
        header = file.read(8)  # 4 bytes ID + 4 bytes size
        if len(header) < 8:
            return None  # EOF reached
        chunk_id, chunk_size = struct.unpack("<II", header)
        data = file.read(chunk_size)
        return OVOChunk(chunk_id, chunk_size, data)

# ====================================
#   OVO Importer
# ====================================
class OVOImporter:
    """
    Handles reading and parsing of OVO files.
    """
    def __init__(self, filepath):
        self.filepath = filepath
        self.chunks = []
        self.materials = {}
        self.texture_directory = os.path.dirname(filepath)

    def read_ovo_file(self):
        with open(self.filepath, "rb") as file:
            while True:
                chunk = OVOChunk.read_chunk(file)
                if chunk is None:
                    break
                self.chunks.append(chunk)
        print(f"Successfully read {len(self.chunks)} chunks from {self.filepath}")
        return True

    def import_scene(self):
        if not self.read_ovo_file():
            return {'CANCELLED'}

        scene = OVOScene()

        # --- Load Materials (chunk ID 9) ---
        for chunk in self.chunks:
            if chunk.chunk_id == 9:
                material = OVOMaterial.parse_material(chunk.data)
                material.blender_material = material.create_blender_material(self.texture_directory)
                self.materials[material.name] = material

        # --- Create a dedicated global root object ---
        global_root_obj = bpy.data.objects.new("OVO_Root", None)
        bpy.context.collection.objects.link(global_root_obj)
        scene.root = OVONode("OVO_Root", mathutils.Matrix.Identity(4))
        # Store the Blender object reference for the root (optional)
        scene.root.blender_object = global_root_obj

        # --- Process Pure Node Chunks (chunk ID 1) ---
        # For every node chunk, we parse the node tree and attach it as a child of our global root.
        for chunk in self.chunks:
            if chunk.chunk_id == 1:
                file_obj = io.BytesIO(chunk.data)
                node = scene.parse_scene_from_file(file_obj)
                if node:
                    # Attach the parsed node to our global root
                    scene.root.add_child(node)
                    child_obj = bpy.data.objects.get(node.name)
                    if child_obj:
                        child_obj.parent = global_root_obj

        # --- Process Lights (chunk ID 16) ---
        for chunk in self.chunks:
            if chunk.chunk_id == 16:
                light = OVOLight.parse_light(chunk.data)
                light.create_blender_light()

        # --- Process Meshes (chunk ID 18) ---
        for chunk in self.chunks:
            if chunk.chunk_id == 18:
                mesh = OVOMesh.parse_mesh(chunk.data)
                mesh_obj = mesh.create_blender_mesh()
                if mesh.material in self.materials:
                    mat = self.materials[mesh.material]
                    if mat.blender_material:
                        mat.apply_to_mesh(mesh_obj)

        return {'FINISHED'}

# ====================================
#  Blender Import Operator
# ====================================
class OT_ImportOVO(Operator, ImportHelper):
    """
    Blender operator to handle OVO file import.
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
    try:
        bpy.utils.unregister_class(OT_ImportOVO)
        bpy.types.TOPBAR_MT_file_import.remove(menu_func_import)
        print("Successfully unregistered OVO Importer.")
    except Exception as e:
        print(f"⚠Warning: Failed to unregister properly - {e}")

if __name__ == "__main__":
    register()

# ====================================
#  OVO Object Hierarchy
# ====================================
class OVOObject:
    """
    Base class for all OVO objects in the scene hierarchy.
    """
    def __init__(self, name, matrix):
        self.name = name
        self.matrix = matrix  # 4x4 transformation matrix
        self.children = []

    def add_child(self, child):
        self.children.append(child)

class OVONode(OVOObject):
    """
    Represents a generic node in the OVO scenegraph.
    """
    def __init__(self, name, matrix):
        super().__init__(name, matrix)

# ====================================
#  OVO Mesh Class
# ====================================
class OVOMesh(OVONode):
    """
    Represents a 3D mesh node.
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
        file = io.BytesIO(chunk_data)
        mesh_name = OVOScene._read_string(file)
        print(f"\nProcessing MESH: {mesh_name}")

        # Read transformation matrix (16 floats)
        matrix_values = struct.unpack('16f', file.read(64))
        transformation_matrix = mathutils.Matrix([matrix_values[i:i+4] for i in range(0, 16, 4)])
        print(f"Transformation Matrix:\n{transformation_matrix}")

        num_children = struct.unpack('I', file.read(4))[0]
        print(f"Number of children: {num_children}")

        target_node = OVOScene._read_string(file)
        mesh_subtype = struct.unpack('B', file.read(1))[0]
        print(f"Mesh Subtype: {mesh_subtype}")

        material_name = OVOScene._read_string(file)
        print(f"Material: {material_name}")

        radius = struct.unpack('f', file.read(4))[0]
        min_box = struct.unpack('3f', file.read(12))
        max_box = struct.unpack('3f', file.read(12))
        print(f"Bounding Box Min: {min_box}, Max: {max_box}, Radius: {radius}")

        physics_flag = struct.unpack('B', file.read(1))[0]
        print(f"Physics Flag: {physics_flag}")

        lod_count = struct.unpack('I', file.read(4))[0]
        print(f"Number of LODs: {lod_count}")

        vertex_count, face_count = struct.unpack('2I', file.read(8))
        print(f"Vertices: {vertex_count}, Faces: {face_count}")

        vertices, normals, uvs, faces = [], [], [], []
        for _ in range(vertex_count):
            pos = struct.unpack('3f', file.read(12))
            normal_data = struct.unpack('I', file.read(4))[0]
            uv_data = struct.unpack('I', file.read(4))[0]
            tangent = struct.unpack('I', file.read(4))[0]  # Not used here

            nx = ((normal_data & 0x3FF) / 511.0) * 2.0 - 1.0
            ny = (((normal_data >> 10) & 0x3FF) / 511.0) * 2.0 - 1.0
            nz = (((normal_data >> 20) & 0x3FF) / 511.0) * 2.0 - 1.0
            normal = (nx, ny, nz)

            u = ((uv_data & 0xFFFF) / 65535.0)
            v = (((uv_data >> 16) & 0xFFFF) / 65535.0)
            uv = (u, v)

            vertices.append(pos)
            normals.append(normal)
            uvs.append(uv)

        print(f"Read {len(vertices)} vertices.")

        for _ in range(face_count):
            face = struct.unpack('3I', file.read(12))
            faces.append(face)
        print(f"Read {len(faces)} faces.")

        return OVOMesh(mesh_name, transformation_matrix, material_name, vertices, normals, uvs, faces)

    def create_blender_mesh(self):
        if len(self.faces) == 0:
            print(f"Warning: Mesh {self.name} has no faces.")

        mesh_data = bpy.data.meshes.new(self.name)
        if self.vertices and self.faces:
            mesh_data.from_pydata(self.vertices, [], self.faces)
        else:
            print(f"Error: Mesh {self.name} has no valid faces.")

        if self.normals:
            mesh_data.validate()
            mesh_data.update()
            mesh_data.normals_split_custom_set_from_vertices(self.normals)

        if self.uvs:
            uv_layer = mesh_data.uv_layers.new()
            for i, loop in enumerate(mesh_data.loops):
                uv_layer.data[i].uv = self.uvs[loop.vertex_index]

        obj = bpy.data.objects.new(self.name, mesh_data)
        corrected_matrix = OVOScene()._convert_matrix(self.matrix)
        obj.matrix_world = corrected_matrix
        bpy.context.collection.objects.link(obj)
        print(f"Blender Mesh Created: {self.name}, Vertices: {len(self.vertices)}, Faces: {len(self.faces)}")
        self.blender_object = obj
        return obj

# ====================================
#  OVO Material Class
# ====================================
class OVOMaterial:
    def __init__(self, name, base_color, roughness, metallic, transparency, emissive, textures):
        self.name = name
        self.base_color = base_color
        self.roughness = roughness
        self.metallic = metallic
        self.transparency = transparency
        self.emissive = emissive
        self.textures = textures
        self.blender_material = None

    @staticmethod
    def parse_material(chunk_data):
        file = io.BytesIO(chunk_data)
        name = OVOScene._read_string(file)
        emissive = struct.unpack("<3f", file.read(12))
        base_color = struct.unpack("<3f", file.read(12))
        roughness = struct.unpack("<f", file.read(4))[0]
        metallic = struct.unpack("<f", file.read(4))[0]
        transparency = struct.unpack("<f", file.read(4))[0]
        textures = {}
        texture_types = ["albedo", "normal", "height", "roughness", "metalness"]
        for texture_type in texture_types:
            texture_name = OVOScene._read_string(file)
            textures[texture_type] = texture_name if texture_name != "[none]" else None
        return OVOMaterial(name, base_color, roughness, metallic, transparency, emissive, textures)

    def create_blender_material(self, texture_directory):
        mat = bpy.data.materials.new(name=self.name)
        mat.use_nodes = True

        # Find the Principled BSDF node
        bsdf = None
        for node in mat.node_tree.nodes:
            if node.type == 'BSDF_PRINCIPLED':
                bsdf = node
                break

        if bsdf is None:
            print(f"Error: Principled BSDF node not found in material {self.name}")
            return mat

        if "Base Color" in bsdf.inputs:
            bsdf.inputs["Base Color"].default_value = (*self.base_color, 1.0)
        if "Roughness" in bsdf.inputs:
            bsdf.inputs["Roughness"].default_value = self.roughness
        if "Metallic" in bsdf.inputs:
            bsdf.inputs["Metallic"].default_value = self.metallic

        if "Alpha" in bsdf.inputs and self.transparency < 1.0:
            mat.blend_method = 'BLEND'
            mat.shadow_method = 'HASHED'
            bsdf.inputs["Alpha"].default_value = self.transparency

        if "Emission" in bsdf.inputs:
            bsdf.inputs["Emission"].default_value = (*self.emissive, 1.0)
        else:
            print(f"Warning: 'Emission' input not found in Principled BSDF for material {self.name}. Skipping emission assignment.")

        self.blender_material = mat
        return mat

    def _add_texture(self, material, bsdf, texture_path, texture_type):
        nodes = material.node_tree.nodes
        links = material.node_tree.links
        tex_image = nodes.new(type="ShaderNodeTexImage")
        tex_image.image = bpy.data.images.load(texture_path)
        tex_image.label = texture_type.capitalize()
        texture_slots = {
            "albedo": "Base Color",
            "normal": "Normal",
            "height": "Displacement",
            "roughness": "Roughness",
            "metalness": "Metallic"
        }
        if texture_type in texture_slots:
            if texture_type == "normal":
                normal_map = nodes.new(type="ShaderNodeNormalMap")
                links.new(tex_image.outputs["Color"], normal_map.inputs["Color"])
                links.new(normal_map.outputs["Normal"], bsdf.inputs["Normal"])
            else:
                links.new(tex_image.outputs["Color"], bsdf.inputs[texture_slots[texture_type]])

    def apply_to_mesh(self, mesh_obj):
        if not self.blender_material:
            print(f"Warning: {self.name} has no Blender material.")
            return
        if not mesh_obj.data.materials:
            mesh_obj.data.materials.append(self.blender_material)
        else:
            mesh_obj.data.materials[0] = self.blender_material

# ====================================
#  OVO Light Class
# ====================================
class OVOLight(OVONode):
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
        file = io.BytesIO(chunk_data)
        name = OVOScene._read_string(file)
        matrix_values = struct.unpack("<16f", file.read(64))
        matrix = mathutils.Matrix([matrix_values[i:i+4] for i in range(0, 16, 4)])
        num_children = struct.unpack("<I", file.read(4))[0]
        target_name = OVOScene._read_string(file)
        light_type = struct.unpack("<B", file.read(1))[0]
        color = struct.unpack("<3f", file.read(12))
        radius = struct.unpack("<f", file.read(4))[0]
        direction = struct.unpack("<3f", file.read(12))
        cutoff = struct.unpack("<f", file.read(4))[0]
        spot_exponent = struct.unpack("<f", file.read(4))[0]
        shadow = struct.unpack("<B", file.read(1))[0]
        volumetric = struct.unpack("<B", file.read(1))[0]
        return OVOLight(name, matrix, light_type, color, radius, direction, cutoff, spot_exponent, shadow, volumetric)

    def create_blender_light(self):
        light_types = {0: 'POINT', 1: 'SUN', 2: 'SPOT'}
        light_data = bpy.data.lights.new(name=self.name, type=light_types.get(self.light_type, 'POINT'))
        light_obj = bpy.data.objects.new(self.name, light_data)
        light_data.color = self.color
        light_data.energy = self.radius * 10
        if self.light_type == 2:
            light_data.spot_size = self.cutoff
            light_data.spot_blend = self.spot_exponent / 10.0
        light_data.use_shadow = bool(self.shadow)
        corrected_matrix = OVOScene()._convert_matrix(self.matrix)
        light_obj.matrix_world = corrected_matrix
        light_obj.location = corrected_matrix.translation
        bpy.context.collection.objects.link(light_obj)
        print(f" Created Light: {self.name} at {light_obj.location}")
        self.blender_object = light_obj
        return light_obj

# ====================================
#  OVO Scene Class
# ====================================
class OVOScene:
    def __init__(self):
        self.root = None

    def parse_scene_from_file(self, file, default_name_prefix="Node", counter=[0]):
        start_pos = file.tell()
        node_name = self._read_string(file)
        if not node_name:
            node_name = f"{default_name_prefix}_{counter[0]}"
            counter[0] += 1
            print(f"Warning: Node name empty. Using {node_name}")
        if file.tell() + 64 > len(file.getbuffer()):
            print("Error: Not enough data for transformation matrix.")
            file.seek(start_pos)
            return None
        matrix_values = struct.unpack("<16f", file.read(64))
        matrix = mathutils.Matrix([matrix_values[i:i+4] for i in range(0, 16, 4)])
        if file.tell() + 4 > len(file.getbuffer()):
            print("Error: Not enough data for child count.")
            file.seek(start_pos)
            return None
        num_children = struct.unpack("<I", file.read(4))[0]
        parent_name = self._read_string(file)
        matrix = self._convert_matrix(matrix)
        node = OVONode(node_name, matrix)
        if node_name in bpy.data.objects:
            blender_obj = bpy.data.objects[node_name]
        else:
            blender_obj = bpy.data.objects.new(node_name, None)
            bpy.context.collection.objects.link(blender_obj)
        blender_obj.matrix_world = matrix
        children_parsed = 0
        while children_parsed < num_children and file.tell() < len(file.getbuffer()):
            child = self.parse_scene_from_file(file, default_name_prefix, counter)
            if child is None:
                break
            node.add_child(child)
            child_obj = bpy.data.objects.get(child.name)
            if child_obj:
                child_obj.parent = blender_obj
            children_parsed += 1
        return node

    @staticmethod
    def _read_string(file):
        chars = []
        while True:
            char = file.read(1)
            if char == b'\x00' or not char:
                break
            chars.append(char)
        return b''.join(chars).decode('utf-8', errors='replace')

    def _convert_matrix(self, matrix):
        print(f"Original OVO Matrix for node:\n{matrix}")
        matrix.transpose()  # Convert from row-major to column-major
        conversion_matrix = mathutils.Matrix([
            [1, 0, 0, 0],
            [0, 0, -1, 0],
            [0, 1, 0, 0],
            [0, 0, 0, 1]
        ])
        converted_matrix = conversion_matrix @ matrix
        print(f"Converted Blender Matrix for node:\n{converted_matrix}")
        return converted_matrix

# ====================================
# Main execution
# ====================================
"""""
if __name__ == "__main__":
    bpy.app.debug = False
    filepath = "C:\\Users\\kevin\\Downloads\\output.ovo"
    if not os.path.exists(filepath):
        print(f"Error: OVO file '{filepath}' not found.")
    else:
        print(f"Loading OVO file: {filepath}")
        importer = OVOImporter(filepath)
        result = importer.import_scene()
        bpy.context.view_layer.update()
        print("Scene update complete.")
        print("Imported objects:")
        for obj in bpy.data.objects:
            print(f"- {obj.name}: {obj.type}, Location: {obj.location}")
        print("Debugging Complete.")
"""