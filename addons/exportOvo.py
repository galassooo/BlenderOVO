# cose per blender
import numpy as np

bl_info = {
    "name": "OVO Format Exporter",
    "author": "Martina Galasso",
    "version": (0, 1),
    "blender": (4, 2, 1),
    "location": "File > Export > OverView Object (.ovo)", 
    "description": "Export the current scene to the OVO file format",
    "category": "Import-Export",
}

#imports
import bpy
import struct
import mathutils
import math
import numpy
from bpy_extras.io_utils import ExportHelper
from bpy.props import StringProperty
from bpy.types import Operator

#enum per i tipi TODO da cambiare con solo quelli usati dal reader
class ChunkType:
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

class OVO_Exporter:
    def __init__(self, context, filepath):
        self.context = context
        self.filepath = filepath
        self.processed_objects = set()
        
    def pack_string(self, string):
        #encode strings in byte and add end char
        return string.encode('utf-8') + b'\0'
    
    def pack_matrix(self, matrix):
        # !!!!!!!!!!!!!!!!!!!! TRANSPOSE IMPORTANTISSIMO !!!!!!!!!!!!!!!!!!!!
        # openGL legge matrici al contrario (guarda slides iniziali su opengl)
        matrix = matrix.transposed()
        return struct.pack('16f', *[x for row in matrix for x in row])
    
    def pack_vector3(self, vector):
        # impacchetta vettore generico
        return struct.pack('3f', vector.x, vector.y, vector.z)

    def pack_normal(self, normal):
        """
        Pack a normal vector using 10-10-10-2 format compatible with glm::packSnorm3x10_1x2
        """
        # Ensure the normal is normalized
        normal = normal.normalized()

        def float_to_snorm10(f):
            # Clamp to [-1, 1]
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

        # Pack mantaining GLM format
        packed = x | (y << 10) | (z << 20)

        return struct.pack('<I', packed)

    def pack_uv(self, uv):
        import struct
        # Valida e correggi le coordinate UV
        uv.x = max(0.0, min(1.0, uv.x))
        uv.y = max(0.0, min(1.0, uv.y))
        u_half = struct.unpack('<H', struct.pack('<e', uv.x))[0]
        v_half = struct.unpack('<H', struct.pack('<e', uv.y))[0]
        packed = (v_half << 16) | u_half
        return struct.pack('<I', packed)

    def write_chunk_header(self, file, chunk_id, chunk_size):
        # write chunk id and size
        file.write(struct.pack('2I', chunk_id, chunk_size))
    
    def write_object_chunk(self, file):
        # Write OVO version chunk (current is 8, check doc)
        chunk_data = struct.pack('I', 8)
        self.write_chunk_header(file, ChunkType.OBJECT, len(chunk_data))
        file.write(chunk_data)
    
    
    def write_material_chunk(self, file, material):
        chunk_data = b'' #byte chunk al posto di una stringa 
        #(altrimenty python con il + tra literal crea una stringa e NON una sequenza di byte)

        # Material name
        chunk_data += self.pack_string(material.name)
        
        # Default values
        emission_color = (0, 0, 0)
        base_color_rgb = (0.8, 0.8, 0.8)
        alpha = 1.0
        roughness = 0.5
        metallic = 0.0
        
        #default files values
        albedo_texture = "[none]"
        normal_texture = "[none]"
        roughness_texture = "[none]"
        metallic_texture = "[none]"
        height_texture = "[none]"
        
        #Traccia da un nodo dello shader (input) al nodo image texture (ShaderNodeTexImage)
        def trace_to_image_node(input_socket):
            """Trace back through node connections to find an image node"""
            #se non ho un nodo (quindi uso canali normali)
            if not input_socket or not input_socket.is_linked:
                return "[none]"
                
            # recupero il nodo
            from_node = input_socket.links[0].from_node
            
            # Debug info
            print(f"Tracing from input: {input_socket.name}")
            print(f"Connected node type: {type(from_node).__name__}")
            
            # Check per ShaderNodeTexImage
            if isinstance(from_node, bpy.types.ShaderNodeTexImage):
                print("Found Image Texture node directly")
                if from_node.image:
                    print(f"Image name: {from_node.image.name}")
                    return from_node.image.name
                return "[none]"
                
            # se non è un nodo immagine, cerca nei suoi input
            if hasattr(from_node, 'inputs'):
                # Lista tutti gli input disponibili (DEBUG)
                print(f"Node inputs: {[input.name for input in from_node.inputs]}")
                
                #cerca nell'input Color come prima cosa
                color_input = from_node.inputs.get('Color')
                if color_input and color_input.is_linked:
                    next_node = color_input.links[0].from_node
                    print(f"Checking Color input, found node type: {type(next_node).__name__}") #DEBUGF
                    if isinstance(next_node, bpy.types.ShaderNodeTexImage):
                        if next_node.image:
                            print(f"Found image in Color input: {next_node.image.name}") #DEBUG
                            return next_node.image.name
                        
                # se non trova image nel Color cerca in other inputs
                for input in from_node.inputs:
                    if input.is_linked:
                        next_node = input.links[0].from_node
                        print(f"Checking input {input.name}, found node type: {type(next_node).__name__}") #DEBUG
                        if isinstance(next_node, bpy.types.ShaderNodeTexImage):
                            if next_node.image:
                                print(f"Found image in input {input.name}: {next_node.image.name}") #DEBUG
                                return next_node.image.name
                            
            print("No image found in node chain") #DEBUG
            return "[none]"
                
        #extract emission
        if material.use_nodes and material.node_tree:
            principled = material.node_tree.nodes.get('Principled BSDF')
            emission_node = material.node_tree.nodes.get('Emission')
            
            #convert emission (da RGBA blender a RGB Ovo)
            if emission_node:
                emission = emission_node.inputs[0].default_value
                emission_color = emission[:3] if len(emission) > 2 else (0, 0, 0) #fallback
                
            if principled:
                # get base color and texture
                base_color_input = principled.inputs.get('Base Color')
                if base_color_input:
                    if base_color_input.is_linked: #SE HO UNO SHADER GRAPH COLLEGATO ->
                        albedo_texture = trace_to_image_node(base_color_input) #trace image node
                    else:
                        base_color = base_color_input.default_value # prendi albedo basato sui canali rgb
                        base_color_rgb = base_color[:3] if len(base_color) > 2 else (0.8, 0.8, 0.8) #fallback
                        alpha = base_color[3] if len(base_color) > 3 else 1.0 #estrazione alpha e fallback in caso
                
                # get other properties (gia in 0-1)
                roughness = principled.inputs['Roughness'].default_value
                metallic = principled.inputs['Metallic'].default_value
                
                # Get textures for other inputs (tracing image node)
                normal_input = principled.inputs.get('Normal')
                if normal_input:
                    normal_texture = trace_to_image_node(normal_input)
                    
                roughness_input = principled.inputs.get('Roughness')
                if roughness_input:
                    roughness_texture = trace_to_image_node(roughness_input)
                    
                metallic_input = principled.inputs.get('Metallic')
                if metallic_input:
                    metallic_texture = trace_to_image_node(metallic_input)
                    
                height_input = principled.inputs.get('Height')
                if height_input:
                    height_texture = trace_to_image_node(height_input)
        
        # Write all the data
        chunk_data += struct.pack('3f', *emission_color)
        chunk_data += struct.pack('3f', *base_color_rgb)
        chunk_data += struct.pack('f', roughness)
        chunk_data += struct.pack('f', metallic)
        chunk_data += struct.pack('f', alpha)
        
        # Write texture paths
        chunk_data += self.pack_string(albedo_texture)
        chunk_data += self.pack_string(normal_texture)
        chunk_data += self.pack_string(height_texture)
        chunk_data += self.pack_string(roughness_texture)
        chunk_data += self.pack_string(metallic_texture)
        
        # Write materal chunk
        self.write_chunk_header(file, ChunkType.MATERIAL, len(chunk_data))
        file.write(chunk_data)

    def write_node_recursive(self, file, obj):
        #scrive nodo e figli ricorsivamente: 
        # se ho:
        # node1
        # |_____node 1a
        # |     |______ node 1b
        # |_____node 2
        #
        # scriverà 1 -> 1a -> 1b -> 2 e via cosi

        if obj in self.processed_objects: # se gia processato skip
            return
        self.processed_objects.add(obj) #altrimenti aggiungo al set
        
        # scrivo prima i materiali se non sono stati ancora scritti
        if obj.type == 'MESH':
            for material_slot in obj.material_slots:
                if material_slot.material and material_slot.material not in self.processed_objects:
                    self.write_material_chunk(file, material_slot.material)
                    self.processed_objects.add(material_slot.material)
        
        # conta i figli effettivi (escludi gli oggetti già processati)
        real_children = [child for child in obj.children if child not in self.processed_objects]
        num_children = len(real_children)

        print(f"Processing object: {obj.name} (Type: {obj.type}) with {num_children} children") #DEBUG

        # scrivo il nodo corrente con il numero corretto di figli
        if obj.type == 'MESH':
            self.write_mesh_chunk(file, obj, num_children)
        elif obj.type == 'LIGHT':
            self.write_light_chunk(file, obj, num_children)
        elif obj.type == 'EMPTY':
            self.write_node_chunk(file, obj, num_children)
        else:
            # per altri tipi (sconosciuti etc..) scrivo nodo base
            self.write_node_chunk(file, obj, num_children)
        
        # processa ricorsivamente i figli
        for child in real_children:
            self.write_node_recursive(file, child)

        
    def write_node_chunk(self, file, obj, num_children):
        """Write a basic node chunk for objects that aren't mesh or light"""
        chunk_data = b'' #binario

        # node name
        chunk_data += self.pack_string(obj.name)
        
        #!!!!!!!!!!!!!! CONVERSIONE MATRICE NODO!!!!!!!!!!!!!!!!!!!

        #copia world matrix
        if obj.parent:

            matrix_world = obj.parent.matrix_world.inverted() @ obj.matrix_world
        else:
            print("___________________________________________PARENT ROOT")
            matrix = obj.matrix_world.copy()
            conversion = mathutils.Matrix.Rotation(math.radians(-90), 4, 'X')
            matrix_world = conversion @ matrix

        
        # Pack della matrice
        chunk_data += self.pack_matrix(matrix_world)
        
        # Number of children
        chunk_data += struct.pack('I', num_children)
        
        # Target node (none for now)
        chunk_data += self.pack_string("[none]") #TODO non so cosa mettere -> chiedere
        
        # Write the chunk
        self.write_chunk_header(file, ChunkType.NODE, len(chunk_data))
        file.write(chunk_data)

    def write_mesh_chunk(self, file, obj, num_children):
        chunk_data = b''

        # Mesh name
        chunk_data += self.pack_string(obj.name)

        # ...
        if obj.parent:

            local_matrix = obj.parent.matrix_world.inverted() @ obj.matrix_world
        else:
            print("___________________________________________PARENT ROOT")
            matrix = obj.matrix_world.copy()
            conversion = mathutils.Matrix.Rotation(math.radians(-90), 4, 'X')
            local_matrix = conversion @ matrix

        # Salva la matrice senza conversioni
        final_matrix = local_matrix
        chunk_data += self.pack_matrix(final_matrix)

        # Children and material data
        chunk_data += struct.pack('I', num_children)
        chunk_data += self.pack_string("[none]")
        chunk_data += struct.pack('B', 0)

        if obj.material_slots and obj.material_slots[0].material:
            chunk_data += self.pack_string(obj.material_slots[0].material.name)
        else:
            chunk_data += self.pack_string("[none]")

        # Get mesh data
        depsgraph = bpy.context.evaluated_depsgraph_get()
        obj_eval = obj.evaluated_get(depsgraph)
        mesh = obj_eval.to_mesh()

        # Create BMesh
        import bmesh
        bm = bmesh.new()
        bm.from_mesh(mesh)
        bmesh.ops.triangulate(bm, faces=bm.faces)

        # Ensure lookup tables are updated
        bm.verts.ensure_lookup_table()
        bm.faces.ensure_lookup_table()
        bm.edges.ensure_lookup_table()

        # Get UV layer
        uv_layer = bm.loops.layers.uv.active

        # Collect UV data for vertex-face pairs
        vertex_face_uvs = {}  # (vertex_idx, face_idx) -> UV
        vertices_data = []  # Lista finale dei vertici
        vertex_map = {}  # Mappa (vertex_idx, uv_key) -> new_vertex_idx

        print("\nAnalizzando mesh...")

        # Collect UVs
        for face in bm.faces:
            for loop in face.loops:
                vertex_face_uvs[(loop.vert.index, face.index)] = loop[uv_layer].uv

        # Process vertices
        for vert in bm.verts:
            # Find unique UVs for this vertex
            vert_uvs = set()
            for face in vert.link_faces:
                uv = vertex_face_uvs[(vert.index, face.index)]
                vert_uvs.add((round(uv.x, 5), round(uv.y, 5)))

            # Create a new vertex for each unique UV
            for uv_key in vert_uvs:
                new_idx = len(vertices_data)
                # Trasforma la normale qui
                transformed_normal = (vert.normal)
                vertices_data.append((vert.co, transformed_normal, mathutils.Vector(uv_key)))
                vertex_map[(vert.index, uv_key)] = new_idx

        print(f"Processati {len(bm.verts)} vertici originali in {len(vertices_data)} vertici finali")

        # Calculate bounding box in world space
        bbox_corners = [final_matrix @ mathutils.Vector(corner) for corner in obj.bound_box]
        min_box = mathutils.Vector(map(min, *((v.x, v.y, v.z) for v in bbox_corners)))
        max_box = mathutils.Vector(map(max, *((v.x, v.y, v.z) for v in bbox_corners)))
        radius = (max_box - min_box).length / 2

        # Write bounding box information
        chunk_data += struct.pack('f', radius)
        chunk_data += self.pack_vector3(min_box)
        chunk_data += self.pack_vector3(max_box)

        # Write physics flag (0 = no physics)
        chunk_data += struct.pack('B', 0)

        # Write LODs (1 = single LOD)
        chunk_data += struct.pack('I', 1)

        # Write vertex and face counts
        chunk_data += struct.pack('I', len(vertices_data))
        chunk_data += struct.pack('I', len(bm.faces))

        # Write vertex data
        for pos, norm, uv in vertices_data:
            chunk_data += self.pack_vector3(pos)
            # Usa direttamente la normale già trasformata
            chunk_data += self.pack_normal(norm)
            chunk_data += self.pack_uv(uv)
            chunk_data += struct.pack('I', 0)  # tangent

        # Write face indices
        for face in bm.faces:
            for loop in face.loops:
                uv = vertex_face_uvs[(loop.vert.index, face.index)]
                uv_key = (round(uv.x, 5), round(uv.y, 5))
                new_idx = vertex_map[(loop.vert.index, uv_key)]
                chunk_data += struct.pack('I', new_idx)

        # Write the complete mesh chunk
        self.write_chunk_header(file, ChunkType.MESH, len(chunk_data))
        file.write(chunk_data)

        # Cleanup
        bm.free()
        obj_eval.to_mesh_clear()
     
    
    def write_light_chunk(self, file, obj, num_children):
        chunk_data = b'' #bin
        light_data = obj.data
        
        print("\nDEBUG SPOT LIGHT EXPORT:") #DEBUG
        print(f"Light name: {obj.name}") #DEBUG
        print(f"Matrix world:\n{obj.matrix_world}") #DEBUG
                
        # Light name
        chunk_data += self.pack_string(obj.name)
        
        # CONVERSIONE COORDINATE LOCALI -> COME MESH GUARDA LI PER COMMENTO

        if obj.parent:

            final_matrix = obj.parent.matrix_world.inverted() @ obj.matrix_world
        else:
            print("___________________________________________PARENT ROOT")
            matrix = obj.matrix_world.copy()
            conversion = mathutils.Matrix.Rotation(math.radians(-90), 4, 'X')
            final_matrix = conversion @ matrix

        chunk_data += self.pack_matrix(final_matrix)
        # num of children
        chunk_data += struct.pack('I', num_children)
        
        # Target node
        chunk_data += self.pack_string("[none]") #TODO chiedere
        
        # get light type
        if light_data.type == 'POINT':
            light_subtype = 0  # OMNI
        elif light_data.type == 'SUN':
            light_subtype = 1  # DIRECTIONAL 
        elif light_data.type == 'SPOT':
            light_subtype = 2  # SPOT
        else:
            light_subtype = 0  # Fallback to OMNI
        
        chunk_data += struct.pack('B', light_subtype)
        
        # light color
        color = light_data.color
        chunk_data += self.pack_vector3(mathutils.Vector(color))
        
        if light_data.type == 'POINT' or light_data.type == 'SPOT':
            radius = getattr(light_data, 'cutoff_distance', 100.0)
        elif light_data.type == 'SUN':
            radius = 10000.0  # Large radius for directional lights TODO modificare ed estrai il campo intensity dalla directional
        else:
            radius = 100.0  # Default fallback

        print(f"Debug - Light: {obj.name}, Type: {light_data.type}, Radius: {radius}")  #DEBUG
        chunk_data += struct.pack('f', radius)

        # direction
        if light_data.type in {'SUN', 'SPOT'}:
            #CODICE SENZA TRASFORMAZIONE
            #rot_mat = obj.matrix_world.to_3x3() 
            #direction = (rot_mat @ mathutils.Vector((0.0, 0.0, -1.0))).normalized()

            #direzione in coordinate Blender
            rot_mat = obj.matrix_world.to_3x3()
            raw_direction = rot_mat @ mathutils.Vector((0.0, 0.0, -1.0))

            #direzione OpenGL
            opengl_direction = mathutils.Vector((-raw_direction.x, raw_direction.z, -raw_direction.y))
            
            direction = opengl_direction.normalized()
        else:
            direction = mathutils.Vector((0.0, 0.0, -1.0)) #fallback
        chunk_data += self.pack_vector3(direction)
        
        # Cutoff angle
        if light_data.type == 'SPOT':
            print(f"Spot size (radians): {light_data.spot_size}") #DEBUG
            print(f"Spot size (degrees): {math.degrees(light_data.spot_size)}") #DEBUG
            print(f"Spot blend: {light_data.spot_blend}") #DEBUG
            
            rot_mat = obj.matrix_world.to_3x3()
            raw_direction = mathutils.Vector((0.0, 0.0, -1.0))
            direction = (rot_mat @ raw_direction).normalized()
            
            cutoff = min(math.degrees(light_data.spot_size / 2), 40.0)
        elif light_data.type == 'SUN':
            cutoff = 0.0  # Directional light
        else:
            cutoff = 180.0  # Point light default 180 (slides)
        chunk_data += struct.pack('f', cutoff)
        
        # spot exponent/falloff
        if light_data.type == 'SPOT':
            # spot_blend in Blender va da 0 a 1
            spot_exponent =  light_data.spot_blend
        else:
            spot_exponent = 0.0
        chunk_data += struct.pack('f', spot_exponent)
        
        # Cast shadows flag
        cast_shadows = 1 if light_data.use_shadow else 0
        chunk_data += struct.pack('B', cast_shadows)
        
        # volumetric flag
        chunk_data += struct.pack('B', 0) #TODO chiedi
        
        self.write_chunk_header(file, ChunkType.LIGHT, len(chunk_data))
        file.write(chunk_data)
    


    def export(self):
        #export fun
        try:
            print("\n=== Starting OVO Export ===") #DEBUG
            print(f"Export path: {self.filepath}") #DEBUG
            
            with open(self.filepath, 'wb') as file:
                # Write object chunk (version)
                self.write_object_chunk(file)
                
                # Process materials first
                print("\nProcessing materials...") #DEBUG
                for material in bpy.data.materials:
                    if material is not None and material not in self.processed_objects:
                        print(f"Processing material: {material.name}") #DEBUG
                        self.write_material_chunk(file, material)
                        self.processed_objects.add(material)
                
                # get all root level objects (quelli orfani)
                root_objects = [obj for obj in bpy.data.objects if obj.parent is None]
                num_roots = len(root_objects)
                
                # write root node first
                chunk_data = b''
                chunk_data += self.pack_string("[root]") 
                chunk_data += self.pack_matrix(mathutils.Matrix.Identity(4))  # suppongo sia corretta la matrice identità a record di logica
                chunk_data += struct.pack('I', num_roots)  # Numero di figli (oggetti root)
                chunk_data += self.pack_string("[none]")  # Target node
                
                # Write root node first
                self.write_chunk_header(file, ChunkType.NODE, len(chunk_data))
                file.write(chunk_data)
                
                #processo tutti i nodi ricorsivamente come figli della root
                print("\nProcessing objects...")
                for obj in root_objects:
                    if obj not in self.processed_objects:
                        print(f"\nProcessing root object: {obj.name} (Type: {obj.type})") #DEBUG
                        self.write_node_recursive(file, obj)
                    
            print("\nExport completed successfully!") #DEBUG
            return True
                
        except Exception as e: #stack trace in caso di exc
            import traceback
            print("\n=== Export Error ===")
            print(f"Error type: {type(e).__name__}")
            print(f"Error message: {str(e)}")
            print("\nStack trace:")
            traceback.print_exc()
            print("===================")
            return False
        
            
class OVO_PT_export_main(Operator, ExportHelper): #proprietà per blender
    bl_idname = "export_scene.ovo"
    bl_label = "Export OVO"
    filename_ext = ".ovo"
    
    filter_glob: StringProperty(
        default="*.ovo",
        options={'HIDDEN'},
    ) # type: ignore
    
    def execute(self, context): #execute fun
        exporter = OVO_Exporter(context, self.filepath)
        if exporter.export():
            self.report({'INFO'}, "Export completed successfully")
            return {'FINISHED'}
        else:
            # Retrieve error
            import sys
            import traceback
            error_message = "".join(traceback.format_exception(*sys.exc_info()))
            self.report({'ERROR'}, f"Export failed. Check system console for details.")
            print(error_message)  # print error on console
            return {'CANCELLED'}

def menu_func_export(self, context):
    #define export menu item
    self.layout.operator(OVO_PT_export_main.bl_idname, text="OverView Object (.ovo)")

def register():
    try:
        bpy.utils.unregister_class(OVO_PT_export_main)
        print("Operator già registrato, deregistrato prima di una nuova registrazione.")
    except RuntimeError:
        print("Operator non era registrato, procedo normalmente.")

    bpy.utils.register_class(OVO_PT_export_main)
    bpy.types.TOPBAR_MT_file_export.append(menu_func_export)

def unregister():
    try:
        bpy.utils.unregister_class(OVO_PT_export_main)
        bpy.types.TOPBAR_MT_file_export.remove(menu_func_export)
    except RuntimeError:
        print("Operator non era registrato, skipping unregister.")


if __name__ == "__main__":
    register()  # Registra l'addon
    print("Addon OVO registrato.")

    try:
        import os

        # Ottieni il percorso della cartella in cui si trova lo script attuale
        script_dir = os.path.dirname(os.path.abspath(__file__))

        # Specifica il percorso del file .blend da caricare
        blend_path = os.path.join(script_dir, "scenes", "scarpa.blend")

        # Carica la scena
        bpy.ops.wm.open_mainfile(filepath=blend_path)
        print(f"Scena caricata da: {blend_path}")

        # Crea un percorso relativo alla cartella dello script per l'output
        output_path = os.path.join(script_dir, "bin", "output.ovo")

        # Esegui l'export con il percorso relativo
        bpy.ops.export_scene.ovo(filepath=output_path)
        print(f"Export completato con successo! File salvato in: {output_path}")

    except Exception as e:
        print(f"Errore durante l'export: {e}")

    unregister()
    print("Addon OVO deregistrato.")
