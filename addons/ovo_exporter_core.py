#imports
from collections import defaultdict
import bpy
import struct
import mathutils
import math

# Importa le classi di supporto (versione con importazioni standard)
try:
    # Per quando eseguito come addon
    from .ovo_types import ChunkType, HullType, GREEN, YELLOW, BLUE, BOLD, RESET, RED
    from .ovo_packer import OVOPacker
    from .ovo_texture_manager import OVOTextureManager
    from .ovo_physics import OVOPhysicsManager
    from .ovo_lod_manager import OVOLodManager
    from .ovo_exporter_mesh import OVOMeshManager
except ImportError:
    # Per quando eseguito direttamente
    from ovo_types import ChunkType, HullType, GREEN, YELLOW, BLUE, BOLD, RESET, RED
    from ovo_packer import OVOPacker
    from ovo_texture_manager import OVOTextureManager
    from ovo_lod_manager import OVOLodManager
    from ovo_physics import OVOPhysicsManager
    from ovo_exporter_mesh import OVOMeshManager

class OVO_Exporter:
    def __init__(self, context, filepath, use_mesh=True, use_light=True, use_legacy_compression=True, flip_textures=True):
        self.context = context
        self.filepath = filepath
        self.use_mesh = use_mesh
        self.use_light = use_light
        self.use_legacy_compression = use_legacy_compression
        self.flip_textures = flip_textures  # Nuovo parametro per il flipping delle texture
        self.processed_objects = set()
        self.basePath = ""

        # Inizializza le classi di supporto
        self.packer = OVOPacker()
        # Passa il parametro flip_textures al texture manager
        self.texture_manager = OVOTextureManager(filepath, use_legacy_compression, flip_textures)
        self.physics_manager = OVOPhysicsManager(self.packer)
        self.mesh_manager = OVOMeshManager(self.packer)


    def should_export_object(self, obj):
        """
        Determina se un oggetto dovrebbe essere esportato in base alle opzioni.
        """
        if not obj:
            return False

        # Controlla il tipo di oggetto
        if obj.type == 'MESH' and not self.use_mesh:
            return False
        if obj.type == 'LIGHT' and not self.use_light:
            return False

        return True

    def write_node_recursive(self, file, obj):
        """
        Writes a node and all its children recursively to the OVO file.
        """
        if obj in self.processed_objects:
            return

        self.processed_objects.add(obj)

        # Count only children that will actually be exported
        valid_children = []
        for child in obj.children:
            if child not in self.processed_objects:
                # Add child only if it should be exported
                if ((child.type == 'MESH' and self.use_mesh) or
                        (child.type == 'LIGHT' and self.use_light) or
                        (child.type not in {'MESH', 'LIGHT'})):
                    valid_children.append(child)

        num_children = len(valid_children)

        # ANSI color codes
        CYAN = '\033[96m'  # For mesh names
        YELLOW = '\033[93m'  # For light names
        GREEN = '\033[92m'  # For other node names
        BOLD = '\033[1m'  # Bold text
        RESET = '\033[0m'  # Reset to default color

        # Determine color based on object type
        if obj.type == 'MESH':
            color = CYAN
        elif obj.type == 'LIGHT':
            color = YELLOW
        else:
            color = GREEN

        # Print node information with colored name
        print(f"\n    [OVOExporter] Processing: {BOLD}{color}{obj.name}{RESET}")
        print(f"      - Type: {obj.type}")
        print(f"      - Children: {num_children}")
        print(f"      - Should export: {self.should_export_object(obj)}")

        # Process materials for meshes
        if obj.type == 'MESH' and self.should_export_object(obj):
            for material_slot in obj.material_slots:
                material = material_slot.material
                if material and material not in self.processed_objects:
                    print(f"      - Writing material: {material.name}")
                    self.write_material_chunk(file, material)
                    self.processed_objects.add(material)

        # Write the node only if it should be exported
        if ((obj.type == 'MESH' and self.use_mesh) or
                (obj.type == 'LIGHT' and self.use_light) or
                (obj.type not in {'MESH', 'LIGHT'})):
            if obj.type == 'MESH':
                print(f"      - Writing mesh chunk")
                self.write_mesh_chunk(file, obj, num_children)
            elif obj.type == 'LIGHT':
                print(f"      - Writing light chunk")
                self.write_light_chunk(file, obj, num_children)
            else:
                print(f"      - Writing node chunk")
                self.write_node_chunk(file, obj, num_children)

        # Process valid children recursively
        for child in valid_children:
            self.write_node_recursive(file, child)

    def write_object_chunk(self, file):
        # Write OVO version chunk (current is 8, check doc)
        chunk_data = struct.pack('I', 8)
        self.packer.write_chunk_header(file, ChunkType.OBJECT, len(chunk_data))
        file.write(chunk_data)

    def write_material_chunk(self, file, material):
        """
        Writes a material chunk to the OVO file.

        Args:
            file: Output file object
            material: Blender material to export
        """
        # ANSI color codes
        MAGENTA = '\033[95m'  # For material names
        BOLD = '\033[1m'  # Bold text
        RESET = '\033[0m'  # Reset to default color

        print(f"\n    [OVOExporter.write_material_chunk] Processing material: '{BOLD}{MAGENTA}{material.name}{RESET}'")
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
                print(f"      - Emission: ({emission_color[0]:.3f}, {emission_color[1]:.3f}, {emission_color[2]:.3f})")

            if principled:
                print("      - Found Principled BSDF node")

                # Base Color and related texture
                base_color_input = principled.inputs.get('Base Color')
                if base_color_input:
                    if base_color_input.is_linked:
                        print("      - Base Color has linked texture")
                        albedo_texture = self.texture_manager.trace_to_image_node(base_color_input, isAlbedo=True)
                        if albedo_texture != "[none]":
                            print(f"      - Albedo texture: '{albedo_texture}'")
                    else:
                        base_color = base_color_input.default_value
                        base_color_rgb = base_color[:3] if len(base_color) > 2 else (0.8, 0.8, 0.8)
                        alpha = base_color[3] if len(base_color) > 3 else 1.0
                        print(
                            f"      - Base Color: ({base_color_rgb[0]:.3f}, {base_color_rgb[1]:.3f}, {base_color_rgb[2]:.3f})")
                        print(f"      - Alpha: {alpha:.3f}")

                # Material properties
                roughness = principled.inputs['Roughness'].default_value
                metallic = principled.inputs['Metallic'].default_value
                print(f"      - Roughness: {roughness:.3f}")
                print(f"      - Metallic: {metallic:.3f}")

                # Other textures (through node tracing)
                normal_input = principled.inputs.get('Normal')
                if normal_input:
                    normal_texture = self.texture_manager.trace_to_image_node(normal_input)
                    if normal_texture != "[none]":
                        print(f"      - Normal texture: '{normal_texture}'")

                roughness_input = principled.inputs.get('Roughness')
                if roughness_input:
                    roughness_texture = self.texture_manager.trace_to_image_node(roughness_input)
                    if roughness_texture != "[none]":
                        print(f"      - Roughness texture: '{roughness_texture}'")

                metallic_input = principled.inputs.get('Metallic')
                if metallic_input:
                    metallic_texture = self.texture_manager.trace_to_image_node(metallic_input)
                    if metallic_texture != "[none]":
                        print(f"      - Metallic texture: '{metallic_texture}'")

                height_input = principled.inputs.get('Height')
                if height_input:
                    height_texture = self.texture_manager.trace_to_image_node(height_input)
                    if height_texture != "[none]":
                        print(f"      - Height texture: '{height_texture}'")
        else:
            print("      - Material has no nodes, using default values")

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
        print("      - Writing material chunk to file")
        self.packer.write_chunk_header(file, ChunkType.MATERIAL, len(chunk_data))
        file.write(chunk_data)

        # ANSI color codes
        MAGENTA = '\033[95m'  # For material names
        BOLD = '\033[1m'  # Bold text
        RESET = '\033[0m'  # Reset to default color

        print(f"    [OVOExporter.write_material_chunk] Completed: '{BOLD}{MAGENTA}{material.name}{RESET}'")
    def write_node_chunk(self, file, obj, num_children):
        """
        Writes a basic node chunk for objects that aren't mesh or light.

        Args:
            file: Output file object
            obj: Blender object to export
            num_children: Number of children for this node
        """
        print(f"\n    [OVOExporter.write_node_chunk] Processing node: '{obj.name}'")
        chunk_data = b''  # binary

        # Node name
        chunk_data += self.packer.pack_string(obj.name)


        # In write_mesh_chunk
        if obj.parent:
            local_bl = obj.matrix_local  
        else:
            local_bl = obj.matrix_world

        final_matrix = self.convert_openGl(local_bl)
        chunk_data += self.packer.pack_matrix(final_matrix)

        # Pack the matrix
        print("      - Matrix transformed and packed")

        # Number of children
        chunk_data += struct.pack('I', num_children)
        print(f"      - Children count: {num_children}")

        # Target node (none for now)
        chunk_data += self.packer.pack_string("[none]")

        # Debug additional information
        if num_children > 0:
            children_names = [child.name for child in obj.children
                              if child not in self.processed_objects
                              and self.should_export_object(child)]
            if children_names:
                print(f"      - Child nodes: {', '.join(f'{name}' for name in children_names)}")

        # Write the chunk
        print("      - Writing node chunk to file")
        self.packer.write_chunk_header(file, ChunkType.NODE, len(chunk_data))
        file.write(chunk_data)
        print(f"    [OVOExporter.write_node_chunk] Completed: '{obj.name}'")

    def convert_openGl(self, matrix):

        matrix_copy = matrix.copy()
        C = mathutils.Matrix(((1,0,0,0),
                      (0,0,1,0),
                      (0,-1,0,0),
                      (0,0,0,1)))
        C_inv = C.transposed() 

        return C @ matrix_copy @ C_inv
    
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
        print(f"\n    [OVOExporter.write_mesh_chunk] Processing mesh: '{obj.name}'")
        chunk_data += self.packer.pack_string(obj.name)

        # In write_mesh_chunk
        if obj.parent:
            local_bl = obj.matrix_local  
        else:
            local_bl = obj.matrix_world

        # Save matrix without additional conversions
        final_matrix = self.convert_openGl(local_bl)
        chunk_data += self.packer.pack_matrix(final_matrix)

        # Children and material data
        chunk_data += struct.pack('I', num_children)
        chunk_data += self.packer.pack_string("[none]")
        chunk_data += struct.pack('B', 0)

                
        # Material assignment
        if obj.material_slots and obj.material_slots[0].material:
            material_name = obj.material_slots[0].material.name
            chunk_data += self.packer.pack_string(material_name)
            print(f"      - Material: '{material_name}'")
        else:
            chunk_data += self.packer.pack_string("[none]")
            print("      - No material assigned")

        # Get mesh data from evaluated object
        print("      - Getting mesh data")
        depsgraph = bpy.context.evaluated_depsgraph_get()
        obj_eval = obj.evaluated_get(depsgraph)
        mesh = obj_eval.to_mesh()

        radius, min_box, max_box = self.mesh_manager.get_box_radius(mesh.vertices)

        # Write bounding box information
        chunk_data += struct.pack('f', radius)
        chunk_data += self.packer.pack_vector3(min_box)
        chunk_data += self.packer.pack_vector3(max_box)

        # Process physics data
        print("      - Processing physics data")
        chunk_data = self.physics_manager.write_physics_data(obj, chunk_data)
        lod_manager = OVOLodManager()

        # Check face count to determine if we need multi-LOD
        should_multi_lod = lod_manager.should_generate_multi_lod(obj)

        if should_multi_lod:
            print("      - Generating multiple LODs for high-poly mesh")
            # Generate LOD meshes
            lod_meshes = lod_manager.generate_lod_meshes(obj)

            # Write LOD data
            chunk_data = self.mesh_manager.write_lod_data(obj, chunk_data, lod_meshes)

            # Clean up LOD meshes
            lod_manager.cleanup_lod_meshes(lod_meshes)
        else:
            # Original single LOD code path
            # Write LODs (1 = single LOD)
            chunk_data += struct.pack('I', 1)
            print("      - LOD count: 1 (single LOD)")

            # Create BMesh for the mesh
            import bmesh
            bm = bmesh.new()
            try:
                # Assicuriamoci che la mesh sia ancora valida
                if mesh is not None:
                    # Crea una copia temporanea
                    temp_mesh = bpy.data.meshes.new(f"temp_mesh_{obj.name}")
                    temp_mesh.from_mesh(mesh)
                    
                    # Ora usa il BMesh con la mesh temporanea
                    bm.from_mesh(temp_mesh)
                    bmesh.ops.triangulate(bm, faces=bm.faces)
                    
                    # Get UV layer
                    uv_layer = bm.loops.layers.uv.active
                    if uv_layer:
                        print(f"      - UV layer found: '{mesh.uv_layers.active.name if mesh.uv_layers.active else 'default'}'")
                    else:
                        print("      - WARNING: No UV layer found")
                    
                    # Process mesh geometry
                    vertices_data, face_indices, vertex_count, face_count = self.mesh_manager.process_mesh_geometry(temp_mesh, bm, uv_layer)
                    
                    # Write mesh data to chunk
                    chunk_data = self.mesh_manager.write_mesh_data(chunk_data, vertices_data, face_indices, vertex_count, face_count)
                    
                    # Cleanup
                    bpy.data.meshes.remove(temp_mesh)
                else:
                    # Fallback: se la mesh è invalida, scrivi 0 vertici e 0 facce
                    print("      - WARNING: mesh is invalid, writing empty geometry")
                    chunk_data += struct.pack('I', 0)  # vertex_count = 0
                    chunk_data += struct.pack('I', 0)  # face_count = 0
            except Exception as e:
                print(f"      - ERROR processing mesh: {str(e)}")
                # Fallback: in caso di errore, scrivi 0 vertici e 0 facce
                chunk_data += struct.pack('I', 0)  # vertex_count = 0
                chunk_data += struct.pack('I', 0)  # face_count = 0
            finally:
                bm.free()

        # Write the complete mesh chunk
        print("      - Writing mesh chunk to file")
        self.packer.write_chunk_header(file, ChunkType.MESH, len(chunk_data))
        file.write(chunk_data)

        # Cleanup
        obj_eval.to_mesh_clear()
        print(f"    [OVOExporter.write_mesh_chunk] Completed: '{obj.name}'")

    def write_light_chunk(self, file, obj, num_children):
        """
        Writes a light chunk to the OVO file.

        Args:
            file: Output file object
            obj: Blender light object to export
            num_children: Number of children for this node
        """
        # ANSI color codes
        YELLOW = '\033[93m'  # For light names
        BOLD = '\033[1m'  # Bold text
        RESET = '\033[0m'  # Reset to default color

        print(f"\n    [OVOExporter.write_light_chunk] Processing light: '{BOLD}{YELLOW}{obj.name}{RESET}'")
        chunk_data = b''  # binary
        light_data = obj.data

        # Map light types to readable names
        light_type_names = {
            'POINT': 'Point',
            'SUN': 'Directional',
            'SPOT': 'Spot',
            'AREA': 'Area'
        }
        print(f"      - Light type: {light_type_names.get(light_data.type, light_data.type)}")

        # Light name
        chunk_data += self.packer.pack_string(obj.name)

        # Matrix conversion - as with mesh, see there for comments
        # Matrix with translation only, no rotation
        final_matrix = mathutils.Matrix.Identity(4)

        # Get position and apply it to the matrix
        # Calcola e salva la matrice completa, non solo la traslazione
        # Matrix conversion
        # In write_mesh_chunk
        if obj.parent:
            local_bl = obj.matrix_local  
        else:
            local_bl = obj.matrix_world

        # Save matrix without additional conversions
        local_matrix = self.convert_openGl(local_bl)
        chunk_data += self.packer.pack_matrix(local_matrix)

        # Number of children
        chunk_data += struct.pack('I', num_children)
        print(f"      - Children count: {num_children}")

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
        print(f"      - Light subtype: {subtype_name} (code: {light_subtype})")

        # Light color
        color = light_data.color
        chunk_data += self.packer.pack_vector3(mathutils.Vector(color))
        print(f"      - Color: ({color[0]:.3f}, {color[1]:.3f}, {color[2]:.3f})")

        # Light radius
        if light_data.type == 'POINT':
            radius = getattr(light_data, 'cutoff_distance', 100.0)
        elif light_data.type == 'SUN':
            radius = 0  # According to 3ds Max exporter for graphics project
        elif light_data.type == 'SPOT':
            radius = math.degrees(light_data.spot_size)
        else:
            radius = 90.0  # Default fallback

        chunk_data += struct.pack('f', radius)
        print(f"      - Radius: {radius:.3f}")

        # Light direction
        # In write_light_chunk
        if light_data.type in {'SUN', 'SPOT'}:
            # Vettore base che punta "in avanti" in Blender (asse -Z)
            base_direction = mathutils.Vector((0.0, 0.0, -1.0))

            # Applica la rotazione della luce per ottenere la direzione effettiva
            # in cui punta la luce nel sistema di coordinate di Blender
            rot_mat = obj.matrix_world.to_3x3()
            blender_direction = rot_mat @ base_direction

            # Applica la conversione dal sistema di coordinate di Blender a OpenGL
            conversion = mathutils.Matrix.Rotation(math.radians(-90), 3, 'X')
            opengl_direction = conversion @ blender_direction

            # Normalizza e salva
            direction = opengl_direction.normalized()
            print(
                f"      - Light direction (in OpenGL coords): ({direction.x:.3f}, {direction.y:.3f}, {direction.z:.3f})")
        else:
            # Per luci non direzionali
            direction = mathutils.Vector((0.0, 0.0, -1.0))

        chunk_data += self.packer.pack_vector3(direction)

        # Cutoff angle
        if light_data.type == 'SPOT':
            print(f"      - Spot size (radians): {light_data.spot_size:.3f}")
            print(f"      - Spot size (degrees): {math.degrees(light_data.spot_size):.3f}")
            print(f"      - Spot blend: {light_data.spot_blend:.3f}")

            cutoff = min(math.degrees(light_data.spot_size / 2), 40.0)
        elif light_data.type == 'SUN':
            cutoff = light_data.angle # Directional light
        else:
            cutoff = 180.0  # Point light default 180 (slides)

        chunk_data += struct.pack('f', cutoff)
        print(f"      - Cutoff angle: {cutoff:.3f} degrees")

        # Spot exponent/falloff
        if light_data.type == 'SPOT':
            # Spot_blend in Blender goes from 0 to 1
            spot_exponent = light_data.spot_blend
        else:
            spot_exponent = 0.0

        chunk_data += struct.pack('f', spot_exponent)
        print(f"      - Spot exponent: {spot_exponent:.3f}")

        # Cast shadows flag
        cast_shadows = 1 if light_data.use_shadow else 0
        chunk_data += struct.pack('B', cast_shadows)
        print(f"      - Cast shadows: {'Yes' if cast_shadows else 'No'}")

        # Volumetric flag
        volumetric = 0  # TODO: ask about this
        chunk_data += struct.pack('B', volumetric)
        print(f"      - Volumetric: {'Yes' if volumetric else 'No'}")

        # Write the chunk
        print("      - Writing light chunk to file")
        self.packer.write_chunk_header(file, ChunkType.LIGHT, len(chunk_data))
        file.write(chunk_data)
        print(f"    [OVOExporter.write_light_chunk] Completed: '{BOLD}{YELLOW}{obj.name}{RESET}'")

    def export(self):
        """
        Main export function that coordinates the OVO export process.

        Returns:
            bool: True if export was successful, False otherwise
        """
        try:
            print("\n============================================================")
            print("                   STARTING OVO EXPORT                       ")
            print("============================================================")
            print(f"[OVOExporter] Export path: {self.filepath}")
            print(f"[OVOExporter] Export settings:")
            print(f"    - Use mesh: {self.use_mesh}")
            print(f"    - Use light: {self.use_light}")
            print(f"    - Use legacy compression: {self.use_legacy_compression}")

            with open(self.filepath, 'wb') as file:
                # Write object chunk (version)
                print("\n[OVOExporter] Writing file header (version chunk)")
                self.write_object_chunk(file)

                # Process materials first
                print("\n[OVOExporter] PROCESSING MATERIALS")
                print("------------------------------------------------------------")
                material_count = 0

                for material in bpy.data.materials:
                    if material is not None and material not in self.processed_objects:
                        # ANSI color codes
                        MAGENTA = '\033[95m'  # For material names
                        BOLD = '\033[1m'  # Bold text
                        RESET = '\033[0m'  # Reset to default color

                        print(
                            f"\n[OVOExporter] Processing material {material_count + 1}: '{BOLD}{MAGENTA}{material.name}{RESET}'")
                        self.write_material_chunk(file, material)
                        self.processed_objects.add(material)
                        material_count += 1

                print(f"\n[OVOExporter] Completed materials: {material_count} processed")

                # Get root level objects (orphans)
                root_objects = [obj for obj in bpy.data.objects if obj.parent is None]
                num_roots = len(root_objects)
                print(f"\n[OVOExporter] Found {num_roots} root level objects")

                # Write root node
                print("\n[OVOExporter] Writing [root] node")
                chunk_data = b''
                chunk_data += self.packer.pack_string("[root]")
                chunk_data += self.packer.pack_matrix(mathutils.Matrix.Identity(4))
                chunk_data += struct.pack('I', num_roots)
                chunk_data += self.packer.pack_string("[none]")

                self.packer.write_chunk_header(file, ChunkType.NODE, len(chunk_data))
                file.write(chunk_data)

                # Process all nodes recursively as root children
                print("\n[OVOExporter] PROCESSING SCENE HIERARCHY")
                print("------------------------------------------------------------")
                object_count = 0

                for obj in root_objects:
                    if obj not in self.processed_objects:
                        # ANSI color codes based on object type
                        CYAN = '\033[96m'  # For mesh names
                        YELLOW = '\033[93m'  # For light names
                        GREEN = '\033[92m'  # For other node names
                        BOLD = '\033[1m'  # Bold text
                        RESET = '\033[0m'  # Reset to default color

                        # Determine color based on object type
                        if obj.type == 'MESH':
                            color = CYAN
                        elif obj.type == 'LIGHT':
                            color = YELLOW
                        else:
                            color = GREEN

                        print(
                            f"\n[OVOExporter] Processing root object {object_count + 1}: '{BOLD}{color}{obj.name}{RESET}' (Type: {obj.type})")
                        print("------------------------------------------------------------")
                        self.write_node_recursive(file, obj)
                        object_count += 1
                        print("------------------------------------------------------------")

                print(f"\n[OVOExporter] Completed objects: {len(self.processed_objects) - material_count} processed")

            print("\n============================================================")
            print("                 EXPORT COMPLETED SUCCESSFULLY                ")
            print("============================================================")
            print(f"[OVOExporter] Output file: {self.filepath}")
            print(f"[OVOExporter] Total processed:")
            print(f"    - Materials: {material_count}")
            print(f"    - Objects: {len(self.processed_objects) - material_count}")
            print("============================================================\n")
            return True

        except Exception as e:
            import traceback
            print("\n============================================================")
            print("                      EXPORT ERROR                           ")
            print("============================================================")
            print(f"[OVOExporter] Error type: {type(e).__name__}")
            print(f"[OVOExporter] Error message: {str(e)}")
            print("\n[OVOExporter] Stack trace:")
            traceback.print_exc()
            print("============================================================\n")
            return False