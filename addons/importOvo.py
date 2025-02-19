import math
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
    "blender": (4, 0, 0),
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
        chunks (list): List of parsed chunks from the OVO file.
        meshes (list): List of parsed meshes.
        materials (dict): Dictionary storing parsed materials.
        nodes (list): List of parsed nodes.
        lights (list): List of parsed lights.
        object_data (dict): Stores scene-level metadata.
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
        self.object_data = {}  # Stores scene-level metadata$
        self.blender_meshes = []

    ############################# PARSING FROM OVO #############################

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
        if not light_name.strip():
            light_name = f"Unnamed_Light_{len(self.lights)}"  # Assign default name
            print(f"Warning: Missing light name in OVO file. Assigning: {light_name}")

        print(f"\nProcessing LIGHT: {light_name}")

        # Read transformation matrix (16 floats)
        try:
            matrix_values = struct.unpack('16f', file.read(64))
            transformation_matrix = mathutils.Matrix([matrix_values[i:i + 4] for i in range(0, 16, 4)])

            # Validate transformation matrix
            if not all(-1e6 < v < 1e6 for v in matrix_values):  # Limit matrix values
                print("Warning: Unusual transformation matrix detected. Resetting to identity.")
                transformation_matrix = mathutils.Matrix.Identity(4)

        except struct.error:
            print("Error reading transformation matrix. Using identity matrix.")
            transformation_matrix = mathutils.Matrix.Identity(4)

        print(f"Transformation Matrix:\n{transformation_matrix}")

        # Read number of children
        try:
            num_children = struct.unpack('I', file.read(4))[0]
        except struct.error:
            num_children = 0  # Default to 0 if reading fails
        print(f"Number of Children: {num_children}")

        # Read target node
        target_node = self.read_string(file)
        print(f"Target Node: {target_node if target_node else '[none]'}")

        # Read light subtype (0 = Omni, 1 = Directional, 2 = Spot)
        try:
            light_type = struct.unpack('B', file.read(1))[0]
            if light_type not in [0, 1, 2]:
                print(f"Warning: Unknown light type ({light_type}), defaulting to Omni (0).")
                light_type = 0
        except struct.error:
            light_type = 0  # Default to Omni if error
        print(f"Light Type: {['Omni', 'Directional', 'Spot'][light_type]}")

        # Read light color (3 floats)
        try:
            color = struct.unpack('3f', file.read(12))
        except struct.error:
            color = (1.0, 1.0, 1.0)  # Default to white
        print(f"Light Color: {color}")

        # Read radius
        try:
            radius = struct.unpack('f', file.read(4))[0]
        except struct.error:
            radius = 10.0  # Default radius
        print(f"Light Radius: {radius}")

        # Read direction (only relevant for directional and spot lights)
        try:
            direction = struct.unpack('3f', file.read(12))
        except struct.error:
            direction = (0.0, 0.0, -1.0)  # Default downward
        print(f"Light Direction: {direction}")

        # Read cutoff angle (for spot lights)
        try:
            cutoff_angle = struct.unpack('f', file.read(4))[0]
        except struct.error:
            cutoff_angle = 45.0  # Default spot cutoff
        print(f"Cutoff Angle: {cutoff_angle}°")

        # Read spot exponent
        try:
            spot_exponent = struct.unpack('f', file.read(4))[0]
        except struct.error:
            spot_exponent = 1.0  # Default spot exponent
        print(f"Spot Exponent: {spot_exponent}")

        # Read shadow flag (0 = No Shadows, 1 = Shadows)
        try:
            cast_shadows = struct.unpack('B', file.read(1))[0]
        except struct.error:
            cast_shadows = 0  # Default: No Shadows
        print(f"Casts Shadows: {'Yes' if cast_shadows else 'No'}")

        # Read volumetric flag (0 = No Volumetric Light, 1 = Yes)
        try:
            volumetric = struct.unpack('B', file.read(1))[0]
        except struct.error:
            volumetric = 0  # Default: No volumetric
        print(f"Volumetric: {'Yes' if volumetric else 'No'}")

        # Store parsed light
        light_data = {
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
        }

        print(f"Storing Light Data: {light_data}")  # Debugging statement
        self.lights.append(light_data)

        # Ensure we fully read the chunk
        end_position = file.tell()
        remaining_bytes = chunk_size - (end_position - start_position)
        if remaining_bytes > 0:
            print(f"Skipping {remaining_bytes} bytes of padding.")
            file.read(remaining_bytes)  # Skip padding if needed

    def parse_object_chunk(self, file, chunk_size):
        """
        Reads and processes an OBJECT chunk from the OVO file.
        """
        start_position = file.tell()

        # Read the OVO version number (4 bytes)
        ovo_version = struct.unpack('I', file.read(4))[0]
        print(f"\nProcessing OBJECT chunk... OVO Version: {ovo_version}")

        # Read object name
        object_name = self.read_string(file)
        print(f"Object Name: {object_name}")

        # Store parsed object metadata
        self.object_data = {
            "version": ovo_version,
            "name": object_name if object_name else "OVO_Scene_Root"
        }

        # Check if it has a transformation matrix, if it is unusual is being resetted to Identity
        try:
            matrix_values = struct.unpack('16f', file.read(64))
            transformation_matrix = mathutils.Matrix([matrix_values[i:i + 4] for i in range(0, 16, 4)])
            if not all(-1e6 < v < 1e6 for v in matrix_values):  # Limit matrix values
                print("Warning: Unusual transformation matrix detected. Resetting to identity.")
                transformation_matrix = mathutils.Matrix.Identity(4)
        except struct.error:
            print("Error reading transformation matrix. Using identity matrix.")
            transformation_matrix = mathutils.Matrix.Identity(4)

        self.object_data["matrix"] = transformation_matrix
        print(f"Object Transformation Matrix:\n{transformation_matrix}")

        # Ensure we fully read the chunk
        end_position = file.tell()
        remaining_bytes = chunk_size - (end_position - start_position)
        if remaining_bytes > 0:
            file.read(remaining_bytes)  # Skip padding if needed

    def parse_file(self):
        """
        Reads the OVO file structure and processes each chunk based on its type.

        It will iterate over the binary structure of the OVO file, extract relevant data,
        and store it in corresponding attributes.

        Raises:
            FileNotFoundError: If the file does not exist.
            Exception: If any unexpected error occurs during parsing.
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

############################# CONVERTING IN BLENDER #############################

    def create_blender_materials(self):
        """
        Creates Blender materials from parsed OVO material data.
        """
        for mat_name, mat_data in self.materials.items():
            print(f"Creating Material: {mat_name}")

            # Create a new Blender material
            material = bpy.data.materials.new(name=mat_name)
            material.use_nodes = True
            nodes = material.node_tree.nodes
            bsdf = nodes.get("Principled BSDF")

            if bsdf:
                # Set base color
                base_color = mat_data["base_color"]
                bsdf.inputs["Base Color"].default_value = (base_color[0], base_color[1], base_color[2], 1.0)

                # Check if "Emission" exists in the node before setting it
                if "Emission" in bsdf.inputs:
                    emission = mat_data["emission"]
                    bsdf.inputs["Emission"].default_value = (emission[0], emission[1], emission[2], 1.0)
                else:
                    print(f"Warning: 'Emission' not found in {mat_name}")

                # Set roughness & metallic
                bsdf.inputs["Roughness"].default_value = mat_data["roughness"]
                bsdf.inputs["Metallic"].default_value = mat_data["metallic"]

            # Store the created material
            self.materials[mat_name]["blender_material"] = material

    def create_blender_meshes(self):
        """
        Creates Blender mesh objects from parsed OVO mesh data.
        Ensures correct application of transformation matrices.
        """
        for mesh_data in self.meshes:
            print(f"Creating Mesh: {mesh_data['name']}")

            # Step 1: Create a new mesh and object in Blender
            mesh = bpy.data.meshes.new(mesh_data["name"])
            obj = bpy.data.objects.new(mesh_data["name"], mesh)

            # Step 2: Convert OpenGL (Y-up) to Blender (Z-up) by swapping Y and Z axes
            opengl_to_blender = mathutils.Matrix((
                (1, 0, 0, 0),
                (0, 0, -1, 0),  # Swap Y → -Z
                (0, 1, 0, 0),  # Swap Z → Y
                (0, 0, 0, 1)
            ))

            # Step 3: Apply the transformation matrix from the OVO file (converted to Blender's coordinate system)
            obj.matrix_world = opengl_to_blender @ mesh_data["matrix"].transposed()

            # Step 4: Link object to Blender scene
            bpy.context.collection.objects.link(obj)

            # Step 5: Create mesh geometry (vertices and faces)
            mesh.from_pydata(mesh_data["vertices"], [], mesh_data["faces"])
            mesh.update()

            # Step 6: Assign material if available
            material_name = mesh_data["material"]
            if material_name in self.materials:
                material = self.materials[material_name]["blender_material"]
                obj.data.materials.append(material)

            # Step 7: Store created object for further processing
            self.blender_meshes.append(obj)

    def create_blender_lights(self):
        """
        Creates Blender light objects from parsed OVO light data.
        Applies the correct transformation matrix.
        """
        for light_data in self.lights:
            if "name" not in light_data:
                print(f"Warning: Light data missing 'name' key. Skipping: {light_data}")
                continue  # Skip this light if the name is missing

            print(f"Creating Light: {light_data['name']}")

            # Step 1: Determine light type (OVO supports Point, Sun, and Spot)
            light_type = ["POINT", "SUN", "SPOT"][light_data["type"]]

            # Step 2: Create a new light in Blender
            light = bpy.data.lights.new(name=light_data["name"], type=light_type)
            obj = bpy.data.objects.new(light_data["name"], light)

            # Step 3: Convert OpenGL (Y-up) to Blender (Z-up)
            opengl_to_blender = mathutils.Matrix((
                (1, 0, 0, 0),
                (0, 0, -1, 0),  # Swap Y → -Z
                (0, 1, 0, 0),  # Swap Z → Y
                (0, 0, 0, 1)
            ))

            # Step 4: Apply transformation matrix to the light object
            obj.matrix_world = opengl_to_blender @ light_data["matrix"].transposed()

            # Step 5: Link the object to the Blender scene
            bpy.context.collection.objects.link(obj)

            # Step 6: Apply light properties from OVO data
            light.color = light_data["color"]
            light.energy = light_data["radius"] * 10  # Scale brightness based on radius

            if light_type == "SPOT":
                light.spot_size = math.radians(light_data["cutoff"])
                light.spot_blend = light_data["spot_exponent"]

            # Step 7: Store created light for further use
            self.lights.append(obj)

    def create_blender_objects(self):
        """
        Creates Blender objects for the main OVO scene.
        """
        if "name" not in self.object_data:
            print("No root OBJECT found, skipping object creation.")
            return

        object_name = self.object_data["name"]
        print(f"Creating OBJECT: {object_name}")

        # Step 1: Create an empty object in Blender to represent the scene
        obj = bpy.data.objects.new(object_name, None)

        # Step 2: Convert OpenGL (Y-up) to Blender (Z-up)
        opengl_to_blender = mathutils.Matrix((
            (1, 0, 0, 0),
            (0, 0, -1, 0),  # Swap Y → -Z
            (0, 1, 0, 0),  # Swap Z → Y
            (0, 0, 0, 1)
        ))

        # Step 3: Apply transformation matrix with conversion
        obj.matrix_world = opengl_to_blender @ self.object_data["matrix"].transposed()

        # Step 4: Link the object to the Blender scene
        bpy.context.collection.objects.link(obj)

        # Step 5: Store object reference for further use
        self.object_data["blender_object"] = obj

    def apply_parenting(self):
        """
        Applies the correct parent-child hierarchy based on OVO node data.
        This ensures that objects maintain their structure in the scene.
        """
        for node in self.nodes:
            parent_name = node["target"]
            child_name = node["name"]

            # Step 1: Get Blender objects by name
            parent_obj = bpy.data.objects.get(parent_name)
            child_obj = bpy.data.objects.get(child_name)

            # Step 2: If both parent and child exist, establish parent-child relationship
            if parent_obj and child_obj:
                print(f"Parenting {child_name} → {parent_name}")
                child_obj.parent = parent_obj  # Set the child object to be parented to the parent object

    def import_scene(self):
        """
        Parses the OVO file and generates the scene in Blender.
        """
        print("\n=== Importing OVO Scene ===")

        # Step 1: Parse the OVO file to extract all data
        self.parse_file()

        # Step 2: Create objects in Blender in the correct order
        self.create_blender_materials()
        self.create_blender_meshes()
        self.create_blender_lights()
        self.apply_parenting()  # Ensure correct object hierarchy
        self.create_blender_objects()

        print("\n=== Import Complete! ===")

############################# REGISTER FOR BLENDER #############################

class OT_ImportOVO(Operator, ImportHelper):
    """Import an OVO scene file"""
    bl_idname = "import_scene.ovo"
    bl_label = "Import OVO"
    bl_options = {'REGISTER', 'UNDO'}

    filename_ext = ".ovo"
    filter_glob: StringProperty(default="*.ovo", options={'HIDDEN'})

    def execute(self, context):
        """Execute the import process"""
        importer = OVO_Importer(self.filepath)
        importer.import_scene()
        return {'FINISHED'}

# Function to add import option in the File > Import menu
def menu_func(self, context):
    self.layout.operator(OT_ImportOVO.bl_idname, text="OverView Object (.ovo)")

def register():
    """Registers the addon and its components"""
    bpy.utils.register_class(OT_ImportOVO)
    bpy.types.TOPBAR_MT_file_import.append(menu_func)

def unregister():
    """Unregisters the addon and its components"""
    bpy.utils.unregister_class(OT_ImportOVO)
    bpy.types.TOPBAR_MT_file_import.remove(menu_func)

if __name__ == "__main__":
    register()

############################# TESTING MAIN #############################
"""""
if __name__ == "__main__":
    filepath = "C:\\Users\\kevin\\Desktop\\SemesterProject\\addons\\bin\\output.ovo"
    importer = OVO_Importer(filepath)
    importer.import_scene()
    bpy.context.view_layer.update()
    print("Scene update complete.")
"""""