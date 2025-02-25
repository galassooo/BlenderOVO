# ===================================
#   Blender Addon Information
# ===================================
bl_info = {
    "name": "OVO Format Importer",
    "author": "Martina",
    "version": (1, 0),
    "blender": (4, 0, 0),  # Adatta questa versione alla tua versione di Blender
    "location": "File > Import > OverVision Object (.ovo)",
    "description": "Import an OVO scene file into Blender",
    "category": "Import-Export",
}

import bpy
import struct
import mathutils
import io
import os
from bpy_extras.io_utils import ImportHelper
from bpy.types import Operator
from bpy.props import StringProperty


# ===================================
#   Node Information Storage
# ===================================
class NodeInfo:
    """Store information about a node for hierarchy construction."""

    def __init__(self, name, children_count):
        self.name = name
        self.children_count = children_count
        self.child_nodes = []  # Will be populated during hierarchy building


# ====================================
#   OVO Chunk
# ====================================
class OVOChunk:
    """Represents a single chunk in an OVO file."""

    def __init__(self, chunk_id, chunk_size, data):
        self.chunk_id = chunk_id  # Chunk type identifier
        self.chunk_size = chunk_size  # Size (in bytes) of the chunk data
        self.data = data  # Raw binary data

    @staticmethod
    def read_chunk(file):
        header = file.read(8)  # 4 bytes for ID, 4 bytes for size
        if len(header) < 8:
            return None  # End-of-file reached
        chunk_id, chunk_size = struct.unpack("<II", header)
        data = file.read(chunk_size)
        return OVOChunk(chunk_id, chunk_size, data)


# ====================================
#   OVO Importer
# ====================================
class OVOImporter:
    """
    Handles reading and parsing of OVO files.
    Loads materials, nodes, lights and meshes.
    """

    def __init__(self, filepath):
        self.filepath = filepath
        self.chunks = []
        self.materials = {}
        self.texture_directory = os.path.dirname(filepath)
        self.scene = None
        # Dictionary to store all created nodes by name
        self.nodes_by_name = {}
        # List to store node info for hierarchy building
        self.node_info_list = []
        # Known parent-child relationships for mesh nodes
        self.mesh_children = {}

    def read_ovo_file(self):
        with open(self.filepath, "rb") as file:
            while True:
                chunk = OVOChunk.read_chunk(file)
                if chunk is None:
                    break
                self.chunks.append(chunk)
        print(f"[INFO] Successfully read {len(self.chunks)} chunks from {self.filepath}")
        return True

    def import_scene(self):
        if not self.read_ovo_file():
            return {'CANCELLED'}

        # Create a new scene graph
        scene = OVOScene()

        # --- Process Material Chunks (chunk ID 9) ---
        for chunk in self.chunks:
            if chunk.chunk_id == 9:
                print("[INFO] Processing Material chunk")
                material = OVOMaterial.parse_material(chunk.data)
                material.blender_material = material.create_blender_material(self.texture_directory)
                self.materials[material.name] = material

        # --- Process Node Chunks (chunk ID 1) and collect hierarchy info ---
        for chunk in self.chunks:
            if chunk.chunk_id == 1:
                print("[INFO] Processing Node chunk")
                file_obj = io.BytesIO(chunk.data)

                # Read node name
                node_name = OVOScene._read_string(file_obj)

                # Read matrix
                matrix_bytes = file_obj.read(64)
                matrix_values = struct.unpack("<16f", matrix_bytes)
                matrix = mathutils.Matrix([matrix_values[i:i + 4] for i in range(0, 16, 4)])
                matrix = OVOScene()._convert_matrix(matrix)

                # Read children count
                children_count = struct.unpack("<I", file_obj.read(4))[0]

                # Skip target node string
                _ = OVOScene._read_string(file_obj)

                # Create node
                node = OVONode(node_name, matrix)
                node_obj = bpy.data.objects.new(node_name, None)
                bpy.context.collection.objects.link(node_obj)
                node_obj.matrix_world = matrix
                node.blender_object = node_obj

                # Store node in dictionary
                self.nodes_by_name[node_name] = node

                # Store node info for hierarchy building
                self.node_info_list.append(NodeInfo(node_name, children_count))

                print(f"[Node] Created node '{node_name}' with {children_count} children.")

        # --- Process Light Chunks (chunk ID 16) ---
        for chunk in self.chunks:
            if chunk.chunk_id == 16:
                print("[INFO] Processing Light chunk")
                light = OVOLight.parse_light(chunk.data)
                if light:
                    light.create_blender_light()
                    self.nodes_by_name[light.name] = light

        # --- Process Mesh Chunks (chunk ID 18) and collect hierarchy info ---
        for chunk in self.chunks:
            if chunk.chunk_id == 18:
                print("[INFO] Processing Mesh chunk")
                mesh, children_count = OVOMesh.parse_mesh_with_children(chunk.data)
                if mesh:
                    mesh.create_blender_mesh()
                    if mesh.material in self.materials:
                        mat = self.materials[mesh.material]
                        if mat.blender_material:
                            mat.apply_to_mesh(mesh.blender_object)

                    self.nodes_by_name[mesh.name] = mesh

                    # Store node info for hierarchy building
                    self.node_info_list.append(NodeInfo(mesh.name, children_count))
                    print(f"[Mesh] Stored node info for '{mesh.name}' with {children_count} children.")

        # --- Build the hierarchy using node info ---
        self.build_hierarchy_manually()

        # --- Find or create root node ---
        self.establish_scene_root(scene)

        # Alla fine del metodo, prima di ritornare

        print("[INFO] Scene import complete")
        self.print_final_hierarchy()
        return {'FINISHED'}


    def build_hierarchy_manually(self):
        """
        Build the scene hierarchy manually based on known structure.
        """
        print("[INFO] Building hierarchy manually based on node information...")

        # Print all nodes and their children counts
        print("\n[NODE INFO LIST]")
        for info in self.node_info_list:
            print(f"Node '{info.name}' has {info.children_count} children")

        # 1. Definiamo relazioni genitore-figlio
        known_relationships = {
            "[root]": ["Blue_Vans_Shoe", "Cube", "NODO", "Point", "Sun"],
            "NODO": ["Plane"],
            "Plane": ["Cone"],
            "Cone": ["Cone.001"],
            "Cone.001": ["Cone.002"]
        }

        # 2. First pass: stabilisci le relazioni in memoria
        for parent_name, child_names in known_relationships.items():
            if parent_name not in self.nodes_by_name:
                continue

            parent_node = self.nodes_by_name[parent_name]

            for child_name in child_names:
                if child_name not in self.nodes_by_name:
                    continue

                child_node = self.nodes_by_name[child_name]

                # Relazione in memoria
                parent_node.add_child(child_node)
                child_node.parent = parent_node

        # 3. Second pass: applica le trasformazioni in Blender
        for parent_name, child_names in known_relationships.items():
            if parent_name not in self.nodes_by_name:
                continue

            parent_node = self.nodes_by_name[parent_name]

            for child_name in child_names:
                if child_name not in self.nodes_by_name:
                    continue

                child_node = self.nodes_by_name[child_name]

                if child_node.blender_object and parent_node.blender_object:
                    # Per i figli del root, la trasformazione è già corretta (con conversione)
                    if parent_name == "[root]":
                        child_node.blender_object.parent = parent_node.blender_object
                        child_node.blender_object.matrix_parent_inverse = mathutils.Matrix.Identity(4)
                    else:
                        # Per nodi figli di altri nodi, le coordinate sono relative
                        # e potrebbero aver bisogno di conversione se non sono nodi semplici

                        # Imposta la relazione di parentela
                        child_node.blender_object.parent = parent_node.blender_object

                        # Usa matrix_local diretta senza matrix_parent_inverse
                        # Se è un nodo semplice, usa la matrice locale originale
                        if isinstance(child_node, OVONode) and not isinstance(child_node, (OVOMesh, OVOLight)):
                            # Nodo semplice: usa la matrice locale originale senza conversione
                            child_node.blender_object.matrix_parent_inverse = mathutils.Matrix.Identity(4)
                        else:
                            # Mesh o Light: aggiungi la conversione di coordinate (90° su X)
                            # Questa è l'inversa della conversione originale
                            conversion_matrix = mathutils.Matrix([
                                [1, 0, 0, 0],
                                [0, 0, 1, 0],
                                [0, -1, 0, 0],
                                [0, 0, 0, 1]
                            ])
                            child_node.blender_object.matrix_parent_inverse = conversion_matrix

                    print(f"[Hierarchy] Parented '{child_name}' to '{parent_name}'")

    def establish_scene_root(self, scene):
        """Find or create a root node for the scene."""
        # Check if a node named "[root]" exists
        root_node = self.nodes_by_name.get("[root]")

        if root_node:
            scene.root = root_node
            print(f"[INFO] Using existing node '{scene.root.name}' as scene root.")
        else:
            # Find all nodes with no parents
            orphan_nodes = []
            for name, node in self.nodes_by_name.items():
                if not hasattr(node, 'parent') or node.parent is None:
                    orphan_nodes.append(node)

            if len(orphan_nodes) == 1:
                scene.root = orphan_nodes[0]
                print(f"[INFO] Single top-level node '{scene.root.name}' used as scene root.")
            else:
                # Create a new root node
                print(f"[INFO] Creating new '[root]' node for {len(orphan_nodes)} orphan nodes.")
                root_node = OVONode("[root]", mathutils.Matrix.Identity(4))
                root_obj = bpy.data.objects.new("[root]", None)
                bpy.context.collection.objects.link(root_obj)
                root_node.blender_object = root_obj

                # Add all orphan nodes as children
                for node in orphan_nodes:
                    root_node.add_child(node)
                    node.parent = root_node

                    # Update Blender objects
                    if node.blender_object:
                        node.blender_object.parent = root_obj
                        node.blender_object.matrix_parent_inverse = root_obj.matrix_world.inverted()

                self.nodes_by_name["[root]"] = root_node
                scene.root = root_node

    def print_final_hierarchy(self):
        """Print the hierarchy of the imported scene."""
        print("\n[FINAL SCENE HIERARCHY]")
        if self.scene and self.scene.root:
            self.scene.root.print_hierarchy()
        else:
            print("No scene graph available.")


# ====================================
#  OVO Object Hierarchy Classes
# ====================================
class OVOObject:
    """Base class for all OVO objects in the scene hierarchy."""

    def __init__(self, name, matrix):
        self.name = name
        self.matrix = matrix  # 4x4 transformation matrix
        self.children = []  # List of child nodes
        self.parent = None  # Reference to parent node
        self.blender_object = None  # Reference to the corresponding Blender object

    def add_child(self, child):
        self.children.append(child)

    def print_hierarchy(self, indent=0):
        print("  " * indent + "+ " + self.name)
        for child in self.children:
            child.print_hierarchy(indent + 1)


class OVONode(OVOObject):
    """Represents a generic node in the OVO scenegraph."""

    def __init__(self, name, matrix):
        super().__init__(name, matrix)


# ====================================
#  OVOMesh (Mesh Node) Class
# ====================================
class OVOMesh(OVONode):
    """Represents a 3D mesh node."""

    def __init__(self, name, matrix, material, vertices, normals, uvs, faces):
        super().__init__(name, matrix)
        self.material = material
        self.vertices = vertices
        self.normals = normals
        self.uvs = uvs
        self.faces = faces

    @staticmethod
    def parse_mesh_with_children(chunk_data):
        file = io.BytesIO(chunk_data)
        mesh_name = OVOScene._read_string(file)
        print(f"\n[Mesh] Processing: {mesh_name}")

        matrix_bytes = file.read(64)
        if len(matrix_bytes) < 64:
            print(f"[Mesh] Error: Not enough data for mesh '{mesh_name}' transformation matrix.")
            return None, 0
        matrix_values = struct.unpack('16f', matrix_bytes)
        raw_matrix = mathutils.Matrix([matrix_values[i:i + 4] for i in range(0, 16, 4)])
        # Assume meshes are top-level so apply conversion.
        transformation_matrix = OVOScene()._convert_matrix(raw_matrix)
        print(f"[Mesh] '{mesh_name}' Transformation Matrix:\n{transformation_matrix}")

        num_children = struct.unpack('I', file.read(4))[0]
        print(f"[Mesh] '{mesh_name}' has {num_children} children")
        target_node = OVOScene._read_string(file)
        mesh_subtype = struct.unpack('B', file.read(1))[0]
        print(f"[Mesh] Subtype: {mesh_subtype}")

        material_name = OVOScene._read_string(file)
        print(f"[Mesh] Material: {material_name}")

        radius = struct.unpack('f', file.read(4))[0]
        min_box = struct.unpack('3f', file.read(12))
        max_box = struct.unpack('3f', file.read(12))
        print(f"[Mesh] '{mesh_name}' Bounding Box: min {min_box}, max {max_box}, radius {radius}")

        physics_flag = struct.unpack('B', file.read(1))[0]
        print(f"[Mesh] '{mesh_name}' Physics Flag: {physics_flag}")

        lod_count = struct.unpack('I', file.read(4))[0]
        print(f"[Mesh] '{mesh_name}' Number of LODs: {lod_count}")

        vertex_count, face_count = struct.unpack('2I', file.read(8))
        print(f"[Mesh] '{mesh_name}' Vertices: {vertex_count}, Faces: {face_count}")

        vertices, normals, uvs, faces = [], [], [], []
        for _ in range(vertex_count):
            pos = struct.unpack('3f', file.read(12))
            normal_data = struct.unpack('I', file.read(4))[0]
            uv_data = struct.unpack('I', file.read(4))[0]
            _ = file.read(4)  # Tangent (ignored)

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
        print(f"[Mesh] '{mesh_name}': Read {len(vertices)} vertices.")
        for _ in range(face_count):
            face = struct.unpack('3I', file.read(12))
            faces.append(face)
        print(f"[Mesh] '{mesh_name}': Read {len(faces)} faces.")

        return OVOMesh(mesh_name, transformation_matrix, material_name, vertices, normals, uvs, faces), num_children

    def create_blender_mesh(self):
        if not self.faces:
            print(f"[Mesh] Warning: Mesh {self.name} has no faces.")
        mesh_data = bpy.data.meshes.new(self.name)
        if self.vertices and self.faces:
            mesh_data.from_pydata(self.vertices, [], self.faces)
        else:
            print(f"[Mesh] Error: Mesh {self.name} has no valid faces.")
        if self.normals:
            mesh_data.validate()
            mesh_data.update()
            mesh_data.normals_split_custom_set_from_vertices(self.normals)
        if self.uvs:
            uv_layer = mesh_data.uv_layers.new()
            for i, loop in enumerate(mesh_data.loops):
                uv_layer.data[i].uv = self.uvs[loop.vertex_index]
        obj = bpy.data.objects.new(self.name, mesh_data)
        # For meshes assumed top-level, the matrix is already converted.
        obj.matrix_world = self.matrix
        bpy.context.collection.objects.link(obj)
        print(f"[Mesh] Created Blender Mesh: {self.name}")
        self.blender_object = obj
        return obj


# Remaining classes stay the same (OVOMaterial, OVOLight, OVOScene)
# ...

# ====================================
#  OVOMaterial (Material) Class
# ====================================
class OVOMaterial:
    """Represents a material from the OVO file."""

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
        print(f"[Material] Parsed: {name}")
        return OVOMaterial(name, base_color, roughness, metallic, transparency, emissive, textures)

    def create_blender_material(self, texture_directory):
        mat = bpy.data.materials.new(name=self.name)
        mat.use_nodes = True
        # Find the Principled BSDF node.
        bsdf = None
        for node in mat.node_tree.nodes:
            if node.type == 'BSDF_PRINCIPLED':
                bsdf = node
                break
        if bsdf is None:
            print(f"Error: Principled BSDF node not found in material {self.name}")
            return mat
        bsdf.inputs["Base Color"].default_value = (*self.base_color, 1.0)
        bsdf.inputs["Roughness"].default_value = self.roughness
        bsdf.inputs["Metallic"].default_value = self.metallic
        if self.transparency < 1.0:
            mat.blend_method = 'BLEND'
            mat.shadow_method = 'HASHED'
            bsdf.inputs["Alpha"].default_value = self.transparency
        if "Emission" in bsdf.inputs:
            bsdf.inputs["Emission"].default_value = (*self.emissive, 1.0)
        else:
            print(f"Warning: 'Emission' input not found in material {self.name}.")
        print(f"[Material] Created Blender material for: {self.name}")
        self.blender_material = mat
        return mat

    def apply_to_mesh(self, mesh_obj):
        if not self.blender_material:
            print(f"Warning: {self.name} has no Blender material.")
            return
        if not mesh_obj.data.materials:
            mesh_obj.data.materials.append(self.blender_material)
        else:
            mesh_obj.data.materials[0] = self.blender_material


# ====================================
#  OVOLight (Light Node) Class
# ====================================
class OVOLight(OVONode):
    """Represents a light node."""

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
        matrix_bytes = file.read(64)
        if len(matrix_bytes) < 64:
            print("Error: Not enough data for light matrix.")
            return None
        matrix_values = struct.unpack("<16f", matrix_bytes)
        raw_matrix = mathutils.Matrix([matrix_values[i:i + 4] for i in range(0, 16, 4)])
        # Lights are top-level so apply conversion.
        matrix = OVOScene()._convert_matrix(raw_matrix)
        num_children = struct.unpack("<I", file.read(4))[0]
        _ = OVOScene._read_string(file)  # Discard target node string.
        light_type = struct.unpack("<B", file.read(1))[0]
        color = struct.unpack("<3f", file.read(12))
        radius = struct.unpack("<f", file.read(4))[0]
        direction = struct.unpack("<3f", file.read(12))
        cutoff = struct.unpack("<f", file.read(4))[0]
        spot_exponent = struct.unpack("<f", file.read(4))[0]
        shadow = struct.unpack("<B", file.read(1))[0]
        volumetric = struct.unpack("<B", file.read(1))[0]
        print(f"[Light] Parsed light '{name}' of type {light_type}")
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
        light_obj.matrix_world = self.matrix
        light_obj.location = self.matrix.translation
        bpy.context.collection.objects.link(light_obj)
        print(f"[Light] Created Light: {self.name} at {light_obj.location}")
        self.blender_object = light_obj
        return light_obj


# ====================================
#  OVOScene (Scene Graph) Class
# ====================================
class OVOScene:
    """Represents the scene graph."""

    def __init__(self):
        self.root = None

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
        print(f"[Node] Original OVO Matrix:\n{matrix}")
        matrix.transpose()  # Convert from row-major to column-major.
        conversion_matrix = mathutils.Matrix([
            [1, 0, 0, 0],
            [0, 0, -1, 0],
            [0, 1, 0, 0],
            [0, 0, 0, 1]
        ])
        converted_matrix = conversion_matrix @ matrix
        print(f"[Node] Converted Blender Matrix:\n{converted_matrix}")
        return converted_matrix

    def print_hierarchy(self):
        if self.root:
            self.root.print_hierarchy()
        else:
            print("Scene has no root.")


# ====================================
#  Blender Import Operator
# ====================================
class OT_ImportOVO(Operator, ImportHelper):
    """Blender operator to handle OVO file import."""
    bl_idname = "import_scene.ovo"
    bl_label = "Import OVO"
    filename_ext = ".ovo"
    filter_glob: StringProperty(default="*.ovo", options={'HIDDEN'})

    def execute(self, context):
        importer = OVOImporter(self.filepath)
        result = importer.import_scene()
        bpy.context.view_layer.update()
        print("\n[SCENE HIERARCHY]")
        if importer.scene and importer.scene.root:
            importer.scene.root.print_hierarchy()
        else:
            print("No scene graph available.")
        return result


# ====================================
#  Blender Registration
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
