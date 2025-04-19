# ================================================================
# EXPORTER CORE MODULE
# ================================================================
# This module defines the core logic for exporting a Blender scene
# to the OVO format, including chunk creation, data packing, and
# hierarchical traversal of objects.
# ================================================================

# --------------------------------------------------------
# IMPORTS
# --------------------------------------------------------
import bpy
import bmesh
import struct
import mathutils
import math
import traceback

try:
    from .ovo_types import ChunkType, HullType, GREEN, YELLOW, BLUE, BOLD, RESET, RED
    from .ovo_packer import OVOPacker
    from .ovo_texture_manager import OVOTextureManager
    from .ovo_physics import OVOPhysicsManager
    from .ovo_lod_manager import OVOLodManager
    from .ovo_log import log
except ImportError:
    from ovo_types import ChunkType, HullType, GREEN, YELLOW, BLUE, BOLD, RESET, RED
    from ovo_packer import OVOPacker
    from ovo_texture_manager import OVOTextureManager
    from ovo_lod_manager import OVOLodManager
    from ovo_physics import OVOPhysicsManager
    from ovo_log import log

# --------------------------------------------------------
# OVO EXPORTER CLASS
# --------------------------------------------------------
class OVO_Exporter:
    """
        Exports the current Blender scene to the OVO format.
        Handles object traversal, chunk creation, material export, and LOD.
        """

    def __init__(self, context, filepath, use_mesh=True, use_light=True, use_legacy_compression=True, flip_textures=True):
        self.context = context
        self.filepath = filepath
        self.use_mesh = use_mesh
        self.use_light = use_light
        self.use_legacy_compression = use_legacy_compression
        self.flip_textures = flip_textures
        self.processed_objects = set()
        self.basePath = ""

        self.packer = OVOPacker()
        self.texture_manager = OVOTextureManager(filepath, use_legacy_compression, flip_textures)
        self.physics_manager = OVOPhysicsManager(self.packer)

    def should_export_object(self, obj):
        """
        Determines whether an object should be exported based on user settings.
        """
        if not obj:
            return False

        if obj.type == 'MESH' and not self.use_mesh:
            return False
        if obj.type == 'LIGHT' and not self.use_light:
            return False

        return True

    def write_node_recursive(self, file, obj):
        """
        Writes a node and its children recursively into the OVO file.
        """
        if obj in self.processed_objects:
            return

        self.processed_objects.add(obj)

        valid_children = []
        for child in obj.children:
            if child not in self.processed_objects:
                if ((child.type == 'MESH' and self.use_mesh) or
                        (child.type == 'LIGHT' and self.use_light) or
                        (child.type not in {'MESH', 'LIGHT'})):
                    valid_children.append(child)

        num_children = len(valid_children)

        if obj.type == 'MESH':
            category = "MESH"
        elif obj.type == 'LIGHT':
            category = "LIGHT"
        else:
            category = "MESH"

        # Log basic object info
        log(f"[OVOExporter] Processing: {obj.name}", category=category, indent=2)
        log(f"- Type: {obj.type}", category=category, indent=2)
        log(f"- Children: {num_children}", category=category, indent=2)
        log(f"- Should export: {self.should_export_object(obj)}", category=category, indent=2)

        # Process materials for meshes
        if obj.type == 'MESH' and self.should_export_object(obj):
            for material_slot in obj.material_slots:
                material = material_slot.material
                if material and material not in self.processed_objects:
                    log(f"Writing material: {material.name}", category="MATERIAL", indent=3)
                    self.write_material_chunk(file, material)
                    self.processed_objects.add(material)

        # Write the node only if it should be exported
        if ((obj.type == 'MESH' and self.use_mesh) or
                (obj.type == 'LIGHT' and self.use_light) or
                (obj.type not in {'MESH', 'LIGHT'})):
            if obj.type == 'MESH':
                log("Writing mesh chunk", category="MESH", indent=3)
                self.write_mesh_chunk(file, obj, num_children)
            elif obj.type == 'LIGHT':
                log("Writing light chunk", category="LIGHT", indent=3)
                self.write_light_chunk(file, obj, num_children)
            else:
                log("Writing node chunk", category="NODE", indent=3)
                self.write_node_chunk(file, obj, num_children)

        # Process valid children recursively
        for child in valid_children:
            self.write_node_recursive(file, child)

    # --------------------------------------------------------
    # Write Object Chunk
    # --------------------------------------------------------
    def write_object_chunk(self, file):
        """
        Writes the version header chunk for the OVO file.
        """
        chunk_data = struct.pack('I', 8)
        self.packer.write_chunk_header(file, ChunkType.OBJECT, len(chunk_data))
        file.write(chunk_data)

    # --------------------------------------------------------
    # Write Material Chunk
    # --------------------------------------------------------
    def write_material_chunk(self, file, material):
        """
        Writes a material chunk to the OVO file.

        Args:
            file: Output file object
            material: Blender material to export
        """

        log(f"[OVOExporter.write_material_chunk] Processing material: {material.name}", category="MATERIAL", indent=2)
        chunk_data = b''  # byte chunk, not string

        # Material name
        chunk_data += self.packer.pack_string(material.name)

        # Default values
        emission_color = (0, 0, 0)
        base_color_rgb = (0.8, 0.8, 0.8)
        alpha = 1.0
        roughness = 0.5
        metallic = 0.0

        # Default texture file values
        albedo_texture = "[none]"
        normal_texture = "[none]"
        roughness_texture = "[none]"
        metallic_texture = "[none]"
        height_texture = "[none]"

        # Extract material properties
        if material.use_nodes and material.node_tree:
            principled = material.node_tree.nodes.get('Principled BSDF')
            emission_node = material.node_tree.nodes.get('Emission')

            # Emission conversion (from Blender RGBA to RGB for OVO)
            if emission_node:
                emission = emission_node.inputs[0].default_value
                emission_color = emission[:3] if len(emission) > 2 else (0, 0, 0)
                log(f"- Emission: ({emission_color[0]:.3f}, {emission_color[1]:.3f}, {emission_color[2]:.3f})",category="MATERIAL", indent=3)

            if principled:
                log("Found Principled BSDF node", category="MATERIAL", indent=3)

                # Base Color and related texture
                base_color_input = principled.inputs.get('Base Color')
                if base_color_input:
                    if base_color_input.is_linked:
                        log("- Base Color has linked texture", category="MATERIAL", indent=3)
                        albedo_texture = self.texture_manager.trace_to_image_node(base_color_input, isAlbedo=True)
                        if albedo_texture != "[none]":
                            log(f"- Albedo texture: '{albedo_texture}'", category="MATERIAL", indent=3)
                    else:
                        base_color = base_color_input.default_value
                        base_color_rgb = base_color[:3] if len(base_color) > 2 else (0.8, 0.8, 0.8)
                        alpha = base_color[3] if len(base_color) > 3 else 1.0
                        log(f"- Base Color: ({base_color_rgb[0]:.3f}, {base_color_rgb[1]:.3f}, {base_color_rgb[2]:.3f})", category="MATERIAL", indent=3)
                        log(f"- Alpha: {alpha:.3f}", category="MATERIAL", indent=3)

                # Material properties
                roughness = principled.inputs['Roughness'].default_value
                metallic = principled.inputs['Metallic'].default_value
                log(f"- Roughness: {roughness:.3f}", category="MATERIAL", indent=3)
                log(f"- Metallic: {metallic:.3f}", category="MATERIAL", indent=3)

                # Other textures
                normal_input = principled.inputs.get('Normal')
                if normal_input:
                    normal_texture = self.texture_manager.trace_to_image_node(normal_input)
                    if normal_texture != "[none]":
                        log(f"- Normal texture: '{normal_texture}'", category="MATERIAL", indent=3)

                roughness_input = principled.inputs.get('Roughness')
                if roughness_input:
                    roughness_texture = self.texture_manager.trace_to_image_node(roughness_input)
                    if roughness_texture != "[none]":
                        log(f"- Roughness texture: '{roughness_texture}'", category="MATERIAL", indent=3)

                metallic_input = principled.inputs.get('Metallic')
                if metallic_input:
                    metallic_texture = self.texture_manager.trace_to_image_node(metallic_input)
                    if metallic_texture != "[none]":
                        log(f"- Metallic texture: '{metallic_texture}'", category="MATERIAL", indent=3)

                height_input = principled.inputs.get('Height')
                if height_input:
                    height_texture = self.texture_manager.trace_to_image_node(height_input)
                    if height_texture != "[none]":
                        log(f"- Height texture: '{height_texture}'", category="MATERIAL", indent=3)
        else:
            log("- Material has no nodes, using default values", category="MATERIAL", indent=3)

        # Write binary data to chunk
        chunk_data += struct.pack('3f', *emission_color)
        chunk_data += struct.pack('3f', *base_color_rgb)
        chunk_data += struct.pack('f', roughness)
        chunk_data += struct.pack('f', metallic)
        chunk_data += struct.pack('f', alpha)

        # Write texture paths
        chunk_data += self.packer.pack_string(albedo_texture)
        chunk_data += self.packer.pack_string(normal_texture)
        chunk_data += self.packer.pack_string(height_texture)
        chunk_data += self.packer.pack_string(roughness_texture)
        chunk_data += self.packer.pack_string(metallic_texture)

        # Write chunk header and chunk itself to file
        log("Writing material chunk to file", category="MATERIAL", indent=3)
        self.packer.write_chunk_header(file, ChunkType.MATERIAL, len(chunk_data))
        file.write(chunk_data)

        log(f"[OVOExporter.write_material_chunk] Completed: '{material.name}'", category="MATERIAL", indent=2)

    # --------------------------------------------------------
    # Write Node Chunk
    # --------------------------------------------------------
    def write_node_chunk(self, file, obj, num_children):
        """
        Writes a basic node chunk for objects that aren't mesh or light.

        Args:
            file: Output file object
            obj: Blender object to export
            num_children: Number of children for this node
        """
        log(f"[OVOExporter.write_node_chunk] Processing node: '{obj.name}'", category="NODE", indent=2)
        chunk_data = b''

        # Node name
        chunk_data += self.packer.pack_string(obj.name)

        # Matrix conversion
        matrix = obj.matrix_world.copy()
        if obj.parent:
            matrix_world = obj.parent.matrix_world.inverted() @ obj.matrix_world
            log(f"- Has parent: '{obj.parent.name}'", category="NODE", indent=3)
        else:
            log("- No parent (root object)", category="NODE", indent=3)
            conversion = mathutils.Matrix.Rotation(math.radians(-90), 4, 'X')
            matrix_world = conversion @ matrix

        # Pack the matrix
        chunk_data += self.packer.pack_matrix(matrix_world)
        log("- Matrix transformed and packed", category="NODE", indent=3)

        # Number of children
        chunk_data += struct.pack('I', num_children)
        log(f"- Children count: {num_children}", category="NODE", indent=3)

        # Target node
        chunk_data += self.packer.pack_string("[none]")

        # Debug additional information
        if num_children > 0:
            children_names = [child.name for child in obj.children
                              if child not in self.processed_objects
                              and self.should_export_object(child)]
            if children_names:
                joined_names = ', '.join(children_names)
                log(f"- Child nodes: {joined_names}", category="NODE", indent=3)

        # Write the chunk
        log("- Writing node chunk to file", category="NODE", indent=3)
        self.packer.write_chunk_header(file, ChunkType.NODE, len(chunk_data))
        file.write(chunk_data)
        log(f"[OVOExporter.write_node_chunk] Completed: '{obj.name}'", category="NODE", indent=2)

    # --------------------------------------------------------
    # Write Mesh Chunk
    # --------------------------------------------------------
    def write_mesh_chunk(self, file, obj, num_children):
        """
        Writes a mesh chunk to the OVO file.

        Args:
            file: Output file object
            obj: Blender mesh object to export
            num_children: Number of children for this node
        """
        chunk_data = b''

        # Mesh name
        log(f"[OVOExporter.write_mesh_chunk] Processing mesh: '{obj.name}'", category="MESH", indent=2)
        chunk_data += self.packer.pack_string(obj.name)

        # Matrix conversion
        if obj.parent:
            local_matrix = obj.parent.matrix_world.inverted() @ obj.matrix_world
            log(f"- Has parent: '{obj.parent.name}'", category="MESH", indent=3)
        else:
            log("- No parent (root object)", category="MESH", indent=3)
            matrix = obj.matrix_world.copy()
            conversion = mathutils.Matrix.Rotation(math.radians(-90), 4, 'X')
            local_matrix = conversion @ matrix

        # Save matrix without additional conversions
        final_matrix = local_matrix
        chunk_data += self.packer.pack_matrix(final_matrix)

        # Children and material data
        chunk_data += struct.pack('I', num_children)
        chunk_data += self.packer.pack_string("[none]")
        chunk_data += struct.pack('B', 0)

        # Material assignment
        if obj.material_slots and obj.material_slots[0].material:
            material_name = obj.material_slots[0].material.name
            chunk_data += self.packer.pack_string(material_name)
            log(f"- Material: '{material_name}'", category="MESH", indent=3)
        else:
            chunk_data += self.packer.pack_string("[none]")
            log("- No material assigned", category="MESH", indent=3)

        # Get mesh data from evaluated object
        log("- Creating BMesh for triangulation", category="MESH", indent=3)
        depsgraph = bpy.context.evaluated_depsgraph_get()
        obj_eval = obj.evaluated_get(depsgraph)
        mesh = obj_eval.to_mesh()

        # Create BMesh for triangulation
        bm = bmesh.new()
        bm.from_mesh(mesh)
        bmesh.ops.triangulate(bm, faces=bm.faces)

        # Get UV layer
        uv_layer = bm.loops.layers.uv.active
        if uv_layer:
            name = mesh.uv_layers.active.name if mesh.uv_layers.active else "default"
            log(f"- UV layer found: '{name}'", category="MESH", indent=3)
        else:
            log("- WARNING: No UV layer found", category="WARNING", indent=3)

        # Calculate bounding box in world space
        bbox_corners = [final_matrix @ mathutils.Vector(corner) for corner in obj.bound_box]
        min_box = mathutils.Vector(map(min, *((v.x, v.y, v.z) for v in bbox_corners)))
        max_box = mathutils.Vector(map(max, *((v.x, v.y, v.z) for v in bbox_corners)))
        radius = (max_box - min_box).length / 2

        log(f"- Bounding radius: {radius:.4f}", category="MESH", indent=3)
        log(f"- Bounding box min: ({min_box.x:.4f}, {min_box.y:.4f}, {min_box.z:.4f})", category="MESH", indent=3)
        log(f"- Bounding box max: ({max_box.x:.4f}, {max_box.y:.4f}, {max_box.z:.4f})", category="MESH", indent=3)

        # Write bounding box information
        chunk_data += struct.pack('f', radius)
        chunk_data += self.packer.pack_vector3(min_box)
        chunk_data += self.packer.pack_vector3(max_box)

        # Process physics data
        log("- Processing physics data", category="MESH", indent=3)
        chunk_data = self.physics_manager.write_physics_data(obj, chunk_data)
        lod_manager = OVOLodManager()

        # Check face count to determine if we need multi-LOD
        should_multi_lod = lod_manager.should_generate_multi_lod(obj)

        if should_multi_lod:
            log("- Generating multiple LODs for high-poly mesh", category="MESH", indent=3)

            # Generate LOD meshes
            lod_meshes = lod_manager.generate_lod_meshes(obj)

            # Write LOD data
            chunk_data = self.write_lod_data(obj, chunk_data, lod_meshes)

            # Clean up LOD meshes
            lod_manager.cleanup_lod_meshes(lod_meshes)
        else:
            # Original single LOD code path
            # Write LODs (1 = single LOD)
            chunk_data += struct.pack('I', 1)
            log("- LOD count: 1 (single LOD)", category="MESH", indent=3)

            # Collect UV data for vertex-face pairs
            vertex_face_uvs = {}  # (vertex_idx, face_idx) -> UV
            vertices_data = []  # Final list of vertices
            vertex_map = {}  # Map (vertex_idx, uv_key) -> new_vertex_idx

            log("- Analyzing mesh geometry", category="MESH", indent=3)

            # Collect UVs
            for face in bm.faces:
                for loop in face.loops:
                    if uv_layer:
                        vertex_face_uvs[(loop.vert.index, face.index)] = loop[uv_layer].uv

            # Process vertices
            for vert in bm.verts:
                # Find unique UVs for this vertex
                vert_uvs = set()
                for face in vert.link_faces:
                    if (vert.index, face.index) in vertex_face_uvs:
                        uv = vertex_face_uvs[(vert.index, face.index)]
                        vert_uvs.add((round(uv.x, 5), round(uv.y, 5)))

                # Create a new vertex for each unique UV
                for uv_key in vert_uvs:
                    new_idx = len(vertices_data)
                    # Transform normal here
                    transformed_normal = (vert.normal)
                    vertices_data.append((vert.co, transformed_normal, mathutils.Vector(uv_key)))
                    vertex_map[(vert.index, uv_key)] = new_idx

            log(f"- Processed {len(bm.verts)} original vertices into {len(vertices_data)} final vertices",category="MESH", indent=3)
            log(f"- Faces: {len(bm.faces)}", category="MESH", indent=3)

            # Write vertex and face counts
            chunk_data += struct.pack('I', len(vertices_data))
            chunk_data += struct.pack('I', len(bm.faces))

            # Write vertex data
            log(f"- Writing {len(vertices_data)} vertices", category="MESH", indent=3)
            for pos, norm, uv in vertices_data:
                chunk_data += self.packer.pack_vector3(pos)
                # Use already transformed normal directly
                chunk_data += self.packer.pack_normal(norm)
                chunk_data += self.packer.pack_uv(uv)
                chunk_data += struct.pack('I', 0)  # tangent

            # Write face indices
            log(f"- Writing {len(bm.faces)} faces", category="MESH", indent=3)
            for face in bm.faces:
                for loop in face.loops:
                    if (loop.vert.index, face.index) in vertex_face_uvs:
                        uv = vertex_face_uvs[(loop.vert.index, face.index)]
                        uv_key = (round(uv.x, 5), round(uv.y, 5))
                        new_idx = vertex_map[(loop.vert.index, uv_key)]
                        chunk_data += struct.pack('I', new_idx)

        # Write the complete mesh chunk
        log("- Writing mesh chunk to file", category="MESH", indent=3)
        self.packer.write_chunk_header(file, ChunkType.MESH, len(chunk_data))
        file.write(chunk_data)

        # Cleanup
        bm.free()
        obj_eval.to_mesh_clear()
        log(f"[OVOExporter.write_mesh_chunk] Completed: '{obj.name}'", category="MESH", indent=2)

    # --------------------------------------------------------
    # Write LOD Data
    # --------------------------------------------------------
    def write_lod_data(self, obj, chunk_data, lod_meshes):
        """
        Writes LOD data to the chunk.

        Args:
            obj: Blender mesh object
            chunk_data: Current chunk data buffer
            lod_meshes: List of BMesh objects for each LOD

        Returns:
            bytes: Updated chunk data with LOD information
        """
        # Write the number of LODs
        lod_count = len(lod_meshes)
        chunk_data += struct.pack('I', lod_count)
        log(f"- LOD count: {lod_count}", category="MESH", indent=3)

        # Process each LOD level
        for lod_index, bm in enumerate(lod_meshes):
            log(f"- Processing LOD {lod_index + 1}/{lod_count}", category="MESH", indent=3)

            # Collect UV data for vertex-face pairs
            vertex_face_uvs = {}  # (vertex_idx, face_idx) -> UV
            vertices_data = []  # Final list of vertices
            vertex_map = {}  # Map (vertex_idx, uv_key) -> new_vertex_idx

            # Get the UV layer for this specific BMesh
            uv_layer = bm.loops.layers.uv.active
            if uv_layer:
                # Collect UVs
                for face in bm.faces:
                    for loop in face.loops:
                        try:
                            vertex_face_uvs[(loop.vert.index, face.index)] = loop[uv_layer].uv
                        except Exception as e:
                            # If we run into an error, just use default UVs
                            log(f"- Warning: UV access error in LOD {lod_index + 1}: {e}", category="WARNING", indent=4)
                            vertex_face_uvs[(loop.vert.index, face.index)] = mathutils.Vector((0.0, 0.0))

            # Process vertices
            for vert in bm.verts:
                # Find unique UVs for this vertex
                vert_uvs = set()
                for face in vert.link_faces:
                    if (vert.index, face.index) in vertex_face_uvs:
                        uv = vertex_face_uvs[(vert.index, face.index)]
                        vert_uvs.add((round(uv.x, 5), round(uv.y, 5)))

                # If no UVs found add a default UV
                if not vert_uvs and vert.link_faces:
                    vert_uvs.add((0.0, 0.0))

                # Create a new vertex for each unique UV
                for uv_key in vert_uvs:
                    new_idx = len(vertices_data)
                    vertices_data.append((vert.co, vert.normal, mathutils.Vector(uv_key)))
                    vertex_map[(vert.index, uv_key)] = new_idx

            # Write vertex and face counts
            chunk_data += struct.pack('I', len(vertices_data))
            chunk_data += struct.pack('I', len(bm.faces))

            log(f"- LOD {lod_index + 1}: {len(vertices_data)} vertices, {len(bm.faces)} faces", category="MESH", indent=3)

            # Write vertex data
            for pos, norm, uv in vertices_data:
                chunk_data += self.packer.pack_vector3(pos)
                chunk_data += self.packer.pack_normal(norm)
                chunk_data += self.packer.pack_uv(uv)
                chunk_data += struct.pack('I', 0)

            # Write face indices
            for face in bm.faces:
                for loop in face.loops:
                    # Get UV for this vertex-face pair
                    uv_key = (0.0, 0.0)

                    if (loop.vert.index, face.index) in vertex_face_uvs:
                        uv = vertex_face_uvs[(loop.vert.index, face.index)]
                        uv_key = (round(uv.x, 5), round(uv.y, 5))

                    # Get the new vertex index
                    if (loop.vert.index, uv_key) in vertex_map:
                        new_idx = vertex_map[(loop.vert.index, uv_key)]
                        chunk_data += struct.pack('I', new_idx)
                    else:
                        # Fallback for cases where exact UV match isn't found
                        fallback_keys = [k for k in vertex_map.keys() if k[0] == loop.vert.index]
                        if fallback_keys:
                            new_idx = vertex_map[fallback_keys[0]]
                            chunk_data += struct.pack('I', new_idx)
                        else:
                            # This should rarely happen
                            log(f"- WARNING: No mapping found for vertex {loop.vert.index} in LOD {lod_index + 1}",category="WARNING", indent=4)
                            chunk_data += struct.pack('I', 0)

        return chunk_data

    # --------------------------------------------------------
    # Write Light Chunk
    # --------------------------------------------------------
    def write_light_chunk(self, file, obj, num_children):
        """
        Writes a light chunk to the OVO file.

        Args:
            file: Output file object
            obj: Blender light object to export
            num_children: Number of children for this node
        """
        log(f"[OVOExporter.write_light_chunk] Processing light: '{obj.name}'", category="LIGHT", indent=2)
        chunk_data = b''  # binary
        light_data = obj.data

        # Map light types to readable names
        light_type_names = {
            'POINT': 'Point',
            'SUN': 'Directional',
            'SPOT': 'Spot',
            'AREA': 'Area'
        }
        log(f"- Light type: {light_type_names.get(light_data.type, light_data.type)}", category="LIGHT", indent=3)

        # Light name
        chunk_data += self.packer.pack_string(obj.name)

        # Matrix with translation only, no rotation
        final_matrix = mathutils.Matrix.Identity(4)

        # Get position and apply it to the matrix
        if obj.parent:
            matrix_world = obj.parent.matrix_world.inverted() @ obj.matrix_world
        else:
            conversion = mathutils.Matrix.Rotation(math.radians(-90), 4, 'X')
            matrix_world = conversion @ obj.matrix_world.copy()

        chunk_data += self.packer.pack_matrix(matrix_world)

        # Number of children
        chunk_data += struct.pack('I', num_children)
        log(f"- Children count: {num_children}", category="LIGHT", indent=3)

        # Target node
        chunk_data += self.packer.pack_string("[none]")

        # Light subtype
        if light_data.type == 'POINT':
            light_subtype = 0  # OMNI
            subtype_name = "OMNI"
        elif light_data.type == 'SUN':
            light_subtype = 1  # DIRECTIONAL
            subtype_name = "DIRECTIONAL"
        elif light_data.type == 'SPOT':
            light_subtype = 2  # SPOT
            subtype_name = "SPOT"
        else:
            light_subtype = 0  # Fallback to OMNI
            subtype_name = "OMNI (fallback)"

        chunk_data += struct.pack('B', light_subtype)
        log(f"- Light subtype: {subtype_name} (code: {light_subtype})", category="LIGHT", indent=3)

        # Light color
        color = light_data.color
        chunk_data += self.packer.pack_vector3(mathutils.Vector(color))
        log(f"- Color: ({color[0]:.3f}, {color[1]:.3f}, {color[2]:.3f})", category="LIGHT", indent=3)

        # Light radius
        if light_data.type == 'POINT':
            radius = getattr(light_data, 'cutoff_distance', 100.0)
        elif light_data.type == 'SUN':
            radius = 0  # According to 3ds Max exporter for graphics project
        elif light_data.type == 'SPOT':
            radius = math.degrees(light_data.spot_size)
        else:
            radius = 90.0

        chunk_data += struct.pack('f', radius)
        log(f"- Radius: {radius:.3f}", category="LIGHT", indent=3)

        # Light direction
        if light_data.type in {'SUN', 'SPOT'}:
            # Base direction pointing "forward" in Blender (negative Z axis)
            base_direction = mathutils.Vector((0.0, 0.0, -1.0))

            # Apply the light's rotation to get the actual direction
            # in Blender's coordinate system
            rot_mat = obj.matrix_world.to_3x3()
            blender_direction = rot_mat @ base_direction

            # Convert from Blender to OpenGL coordinate system
            conversion = mathutils.Matrix.Rotation(math.radians(-90), 3, 'X')
            opengl_direction = conversion @ blender_direction

            # Normalize and store
            direction = opengl_direction.normalized()
            log(f"- Light direction (OpenGL): ({direction.x:.3f}, {direction.y:.3f}, {direction.z:.3f})",category="LIGHT", indent=3)
        else:
            # For non-directional lights, use a default downward vector
            direction = mathutils.Vector((0.0, 0.0, -1.0))

        chunk_data += self.packer.pack_vector3(direction)

        # Cutoff angle
        if light_data.type == 'SPOT':
            log(f"- Spot size (radians): {light_data.spot_size:.3f}", category="LIGHT", indent=3)
            log(f"- Spot size (degrees): {math.degrees(light_data.spot_size):.3f}", category="LIGHT", indent=3)
            log(f"- Spot blend: {light_data.spot_blend:.3f}", category="LIGHT", indent=3)

            cutoff = min(math.degrees(light_data.spot_size / 2), 40.0)
        elif light_data.type == 'SUN':
            cutoff = 0.0  # Directional light
        else:
            cutoff = 180.0  # Point light default 180 (slides)

        chunk_data += struct.pack('f', cutoff)
        log(f"- Cutoff angle: {cutoff:.3f} degrees", category="LIGHT", indent=3)

        # Spot exponent/falloff
        if light_data.type == 'SPOT':
            # Blender's spot_blend ranges from 0 (sharp) to 1 (soft)
            spot_exponent = light_data.spot_blend
        else:
            spot_exponent = 0.0

        chunk_data += struct.pack('f', spot_exponent)
        log(f"- Spot exponent: {spot_exponent:.3f}", category="LIGHT", indent=3)

        # Shadow flag
        cast_shadows = 1 if light_data.use_shadow else 0
        chunk_data += struct.pack('B', cast_shadows)
        log(f"- Cast shadows: {'Yes' if cast_shadows else 'No'}", category="LIGHT", indent=3)

        # Volumetric flag
        volumetric = 0  #
        chunk_data += struct.pack('B', volumetric)
        log(f"- Volumetric: {'Yes' if volumetric else 'No'}", category="LIGHT", indent=3)

        # Write the chunk
        log("- Writing light chunk to file", category="LIGHT", indent=3)
        self.packer.write_chunk_header(file, ChunkType.LIGHT, len(chunk_data))
        file.write(chunk_data)
        log(f"[OVOExporter.write_light_chunk] Completed: '{obj.name}'", category="LIGHT", indent=2)

    # --------------------------------------------------------
    # Export
    # --------------------------------------------------------
    def export(self):
        """
        Main export function that coordinates the OVO export process.

        Returns:
            bool: True if export was successful, False otherwise
        """
        try:
            log("", category="")
            log("============================================================", category="")
            log("                   STARTING OVO EXPORT", category="")
            log("============================================================", category="")
            log(f"[OVOExporter] Export path: {self.filepath}", category="", indent=1)
            log(f"[OVOExporter] Export settings:", category="", indent=1)
            log(f"- Use mesh: {self.use_mesh}", category="", indent=2)
            log(f"- Use light: {self.use_light}", category="", indent=2)
            log(f"- Use legacy compression: {self.use_legacy_compression}", category="", indent=2)

            with open(self.filepath, 'wb') as file:
                log("", category="", indent=0)
                log("[OVOExporter] Writing file header (version chunk)", category="", indent=1)
                self.write_object_chunk(file)

                # Process materials first
                log("", category="", indent=0)
                log("[OVOExporter] PROCESSING MATERIALS", category="", indent=1)
                log("------------------------------------------------------------", category="", indent=1)
                material_count = 0

                for material in bpy.data.materials:
                    if material is not None and material not in self.processed_objects:
                        log(f"[OVOExporter] Processing material {material_count + 1}: '{material.name}'",category="MATERIAL", indent=2)
                        self.write_material_chunk(file, material)
                        self.processed_objects.add(material)
                        material_count += 1

                log(f"[OVOExporter] Completed materials: {material_count} processed", category="", indent=1)

                # Get root level objects
                root_objects = [obj for obj in bpy.data.objects if obj.parent is None]
                num_roots = len(root_objects)
                log(f"[OVOExporter] Found {num_roots} root level objects", category="", indent=1)

                # Write root node
                log("", category="", indent=0)
                log("[OVOExporter] Writing [root] node", category="NODE", indent=1)
                chunk_data = b''
                chunk_data += self.packer.pack_string("[root]")
                chunk_data += self.packer.pack_matrix(mathutils.Matrix.Identity(4))
                chunk_data += struct.pack('I', num_roots)
                chunk_data += self.packer.pack_string("[none]")

                self.packer.write_chunk_header(file, ChunkType.NODE, len(chunk_data))
                file.write(chunk_data)

                # Process all nodes recursively as root children
                log("", category="", indent=0)
                log("[OVOExporter] PROCESSING SCENE HIERARCHY", category="", indent=1)
                log("------------------------------------------------------------", category="", indent=1)
                object_count = 0

                for obj in root_objects:
                    if obj not in self.processed_objects:
                        if obj.type == 'MESH':
                            category = "MESH"
                        elif obj.type == 'LIGHT':
                            category = "LIGHT"
                        else:
                            category = "MESH"

                        log(f"[OVOExporter] Processing root object {object_count + 1}: '{obj.name}' (Type: {obj.type})",category=category, indent=2)
                        log("------------------------------------------------------------", category="", indent=2)
                        self.write_node_recursive(file, obj)
                        object_count += 1
                        log("------------------------------------------------------------", category="", indent=2)

                log(f"[OVOExporter] Completed objects: {len(self.processed_objects) - material_count} processed",category="", indent=1)

            log("", category="", indent=0)
            log("============================================================", category="")
            log("              EXPORT COMPLETED SUCCESSFULLY", category="")
            log("============================================================", category="")
            log(f"[OVOExporter] Output file: {self.filepath}", category="", indent=1)
            log(f"[OVOExporter] Total processed:", category="", indent=1)
            log(f"- Materials: {material_count}", category="", indent=2)
            log(f"- Objects: {len(self.processed_objects) - material_count}", category="", indent=2)
            log("============================================================\n", category="")
            return True

        except Exception as e:
            log("", category="", indent=0)
            log("============================================================", category="ERROR")
            log("                      EXPORT ERROR", category="ERROR")
            log("============================================================", category="ERROR")
            log(f"[OVOExporter] Error type: {type(e).__name__}", category="ERROR", indent=1)
            log(f"[OVOExporter] Error message: {str(e)}", category="ERROR", indent=1)
            log("[OVOExporter] Stack trace:", category="ERROR", indent=1)
            traceback.print_exc()
            log("============================================================\n", category="ERROR")
            return False