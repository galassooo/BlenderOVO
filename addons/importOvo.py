# ===================================
#   Blender Addon Information
# ===================================
bl_info = {
    "name": "OVO Format Importer",
    "author": "Kevin Quarenghi & Martina Galasso",
    "version": (1, 0),
    "blender": (4, 2, 0),
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

# ------------------------------------------------------------
#   Funzioni di decodifica half-float (u, v) da un uint (32 bit)
# ------------------------------------------------------------

def half_to_float(h: int) -> float:
    """
    @fn half_to_float(h)
    @brief Converte un half-precision float (16 bit) in un float32 Python.
    @param h Valore intero [0..65535] che rappresenta il formato half.
    @return Il valore in floating-point a 32 bit.
    """
    s = (h >> 15) & 0x0001  # sign
    e = (h >> 10) & 0x001F  # exponent
    f =  h        & 0x03FF  # fraction (10 bit)

    if e == 0:
        # subnormal
        val = (f / 1024.0) * (2 ** -14)
    elif e == 31:
        # inf or NaN
        val = float('inf') if f == 0 else float('nan')
    else:
        # normal
        val = (1 + f/1024.0) * (2 ** (e - 15))

    if s == 1:
        val = -val
    return val

def decode_half2x16(packed_uv: int):
    """
    @fn decode_half2x16(packed_uv)
    @brief Decodifica due mezzi float (half) da un singolo uint32.
    @param packed_uv Valore uint32 che contiene due half da 16 bit l'uno.
    @return Una tupla (u, v) in formato float a 32 bit.
    """
    raw_bytes = struct.pack('<I', packed_uv)  # 4 byte
    h1, h2 = struct.unpack('<HH', raw_bytes)  # 2 half
    u = half_to_float(h1)
    v = half_to_float(h2)
    return (u, v)


# ===================================
#   Node Information Storage
# ===================================
class NodeRecord:
    """
    @class NodeRecord
    @brief Memorizza le informazioni relative a un nodo (o mesh o luce) OVO.

    Contiene:
      - name (string): nome del nodo.
      - node_type (str): tipo (NODE, MESH o LIGHT).
      - children_count (int): numero di figli attesi da questo nodo.
      - blender_object (bpy.types.Object): l'oggetto Blender associato.
      - parent (NodeRecord): riferimento al nodo genitore.
      - raw_matrix (mathutils.Matrix): matrice 4x4 letta dal file, in row-major.
    """
    def __init__(self, name, node_type, children_count, blender_object, raw_matrix):
        self.name = name
        self.node_type = node_type
        self.children_count = children_count
        self.blender_object = blender_object
        self.parent = None
        self.raw_matrix = raw_matrix

    def __repr__(self):
        return f"NodeRecord(name={self.name}, type={self.node_type}, children_count={self.children_count})"


# ====================================
#   OVO Chunk
# ====================================
class OVOChunk:
    """
    @class OVOChunk
    @brief Rappresenta un singolo chunk del file OVO, con ID, size e dati binari.
    """
    def __init__(self, chunk_id, chunk_size, data):
        self.chunk_id = chunk_id
        self.chunk_size = chunk_size
        self.data = data

    @staticmethod
    def read_chunk(file):
        """
        @fn read_chunk(file)
        @brief Legge 8 byte per ID e size, poi chunk_size byte di dati.
        @param file File object aperto in binario.
        @return Un OVOChunk o None se siamo a fine file.
        """
        header = file.read(8)
        if len(header) < 8:
            return None
        chunk_id, chunk_size = struct.unpack("<II", header)
        data = file.read(chunk_size)
        return OVOChunk(chunk_id, chunk_size, data)


# ====================================
#   OVO Importer
# ====================================
class OVOImporter:
    """
    @class OVOImporter
    @brief Classe principale che gestisce il parsing di un file OVO e l'import in Blender.

    Flusso:
      1. read_ovo_file(): legge i chunk dal file.
      2. parse_chunks(): crea NodeRecord (nodi, mesh, luci) e materiali.
      3. build_hierarchy_stack_approach(): ricostruisce la gerarchia parent-figlio con uno stack.
      4. establish_root_node(): se non esiste [root], lo crea (se serve).
      5. apply_matrices_with_partial_rotation(): applica trasposizione + rotazione solo ai figli diretti di root.
    """
    def __init__(self, filepath):
        """
        @fn __init__(self, filepath)
        @brief Inizializza l'importer con un percorso al file OVO.
        @param filepath Stringa col percorso del file .ovo
        """
        self.filepath = filepath
        self.chunks = []
        self.materials = {}
        self.texture_directory = os.path.dirname(filepath)
        self.parsed_nodes = []

    def read_ovo_file(self):
        """
        @fn read_ovo_file(self)
        @brief Apre il file e legge tutti i chunk in self.chunks.
        @return True se il file è stato letto con successo, False altrimenti.
        """
        print(f"[OVOImporter] Apertura file: {self.filepath}")
        if not os.path.isfile(self.filepath):
            print(f"[OVOImporter] ERRORE: file non trovato - {self.filepath}")
            return False

        with open(self.filepath, "rb") as file:
            while True:
                chunk = OVOChunk.read_chunk(file)
                if chunk is None:
                    break
                self.chunks.append(chunk)

        print(f"[OVOImporter] Lettura completata. Trovati {len(self.chunks)} chunk.")
        return True

    def import_scene(self):
        """
        @fn import_scene(self)
        @brief Flusso principale di import. Legge il file, costruisce la scena e la gerarchia.
        @return {'FINISHED'} se OK, {'CANCELLED'} se fallisce.
        """
        print(f"[OVOImporter.import_scene] Inizio import del file: {self.filepath}")
        if not self.read_ovo_file():
            return {'CANCELLED'}

        self.parse_chunks()
        self.build_hierarchy_stack_approach()
        self.establish_root_node()
        self.apply_matrices_with_partial_rotation()

        print("[OVOImporter.import_scene] Gerarchia finale importata:")
        self.print_final_hierarchy()
        print("[OVOImporter.import_scene] Import completato con successo.")
        return {'FINISHED'}

    def parse_chunks(self):
        """
        @fn parse_chunks(self)
        @brief Scorre self.chunks e crea materiali e NodeRecord per nodi, mesh, luci.
               Non applica alcuna rotazione. Imposta l'oggetto Blender con matrix_world = Identity.
        """
        print("[OVOImporter.parse_chunks] Inizio analisi chunk.")
        for i, chunk in enumerate(self.chunks):
            cid = chunk.chunk_id
            print(f"  > Chunk #{i} : ID={cid}, size={chunk.chunk_size}")

            # Material
            if cid == 9:
                print("    [INFO] Trovato chunk 'Material'")
                material = OVOMaterial.parse_material(chunk.data)
                mat = material.create_blender_material(self.texture_directory)
                self.materials[material.name] = material
                print(f"    [INFO] Material creato: {material.name}")
                continue

            # Node
            if cid == 1:
                node_name, raw_matrix, children_count = self.parse_node_basic_raw(chunk.data)
                node_obj = bpy.data.objects.new(node_name, None)
                bpy.context.collection.objects.link(node_obj)
                node_obj.matrix_world = mathutils.Matrix.Identity(4)

                record = NodeRecord(node_name, "NODE", children_count, node_obj, raw_matrix)
                self.parsed_nodes.append(record)
                print(f"    [INFO] Creato NodeRecord: {record}")
                continue

            # Light
            if cid == 16:
                light_name, raw_matrix, children_count, light_data = self.parse_light_raw(chunk.data)
                light_obj = bpy.data.objects.new(light_name, light_data)
                bpy.context.collection.objects.link(light_obj)
                light_obj.matrix_world = mathutils.Matrix.Identity(4)

                record = NodeRecord(light_name, "LIGHT", children_count, light_obj, raw_matrix)
                self.parsed_nodes.append(record)
                print(f"    [INFO] Creato NodeRecord: {record}")
                continue

            # Mesh
            if cid == 18:
                mesh_name, raw_matrix, children_count, material_name, mesh_obj, physics_data = self.parse_mesh_raw(
                    chunk.data)

                # Applica il materiale, se presente
                if material_name in self.materials:
                    mat = self.materials[material_name].blender_material
                    if mat:
                        if not mesh_obj.data.materials:
                            mesh_obj.data.materials.append(mat)
                        else:
                            mesh_obj.data.materials[0] = mat

                bpy.context.collection.objects.link(mesh_obj)
                mesh_obj.matrix_world = mathutils.Matrix.Identity(4)

                # Assegna la fisica, se presente
                if physics_data:
                    OVOMesh.apply_physics_to_object(mesh_obj, physics_data)

                record = NodeRecord(mesh_name, "MESH", children_count, mesh_obj, raw_matrix)
                self.parsed_nodes.append(record)
                print(f"    [INFO] Creato NodeRecord: {record}")
                continue

            # Ignorato
            print(f"    [WARNING] Chunk ID={cid} non gestito (ignorato).")

        print("[OVOImporter.parse_chunks] Fine analisi chunk.")

    def build_hierarchy_stack_approach(self):
        """
        @fn build_hierarchy_stack_approach(self)
        @brief Ricostruisce la gerarchia parent-figlio usando uno stack.
               Per ogni NodeRecord, se lo stack top ha children_count>0, set come parent.
        """
        print("[OVOImporter.build_hierarchy_stack_approach] Inizio.")
        stack = []
        for i, record in enumerate(self.parsed_nodes):
            print(f"  >> Elaboro record #{i}: {record}")
            while stack and stack[-1].children_count == 0:
                popped = stack.pop()
                print(f"     [STACK] Rimosso dallo stack: {popped}")

            if stack:
                parent_rec = stack[-1]
                record.parent = parent_rec
                parent_rec.children_count -= 1
                print(f"     [HIER] '{record.name}' figlio di '{parent_rec.name}'. "
                      f"Nuovo children_count={parent_rec.children_count}")

            if record.children_count > 0:
                stack.append(record)
                print(f"     [STACK] Aggiunto allo stack: {record}")

        print("[OVOImporter.build_hierarchy_stack_approach] Impostazione parentela in Blender.")
        for rec in self.parsed_nodes:
            if rec.parent is not None:
                rec.blender_object.parent = rec.parent.blender_object
                rec.blender_object.matrix_parent_inverse = rec.parent.blender_object.matrix_world.inverted()
                print(f"     [BLENDER] '{rec.name}' -> parent = '{rec.parent.name}'")

    def establish_root_node(self):
        """
        @fn establish_root_node(self)
        @brief Se manca un nodo [root] e ci sono più top-level, crea un oggetto root fittizio.
        """
        print("[OVOImporter.establish_root_node] Controllo esistenza '[root]' e nodi top-level.")
        for rec in self.parsed_nodes:
            if rec.name == "[root]":
                print(f"  [INFO] Uso il nodo '[root]' come root esplicito.")
                return

        toplevel = [r for r in self.parsed_nodes if r.parent is None]
        if len(toplevel) > 1:
            print(f"  [INFO] Creo root fittizio. Trovati {len(toplevel)} top-level.")
            root_obj = bpy.data.objects.new("[root]", None)
            bpy.context.collection.objects.link(root_obj)
            for r in toplevel:
                r.blender_object.parent = root_obj
                r.blender_object.matrix_parent_inverse = root_obj.matrix_world.inverted()
                r.parent = None

    def apply_matrices_with_partial_rotation(self):
        """
        @fn apply_matrices_with_partial_rotation(self)
        @brief Applica la conversione di coordinate:
               - Ai figli diretti di [root]: trasposizione + rotazione +90° su X
               - Ai nodi di livello inferiore: sola trasposizione
               - Se un nodo è root, rimane identity.
        """
        print("[OVOImporter] apply_matrices_with_partial_rotation: inizio.")
        for rec in self.parsed_nodes:
            if rec.name == "[root]":
                print(f"   - skip rotation for [root]")
                continue

            # Trasponi la matrice row-major
            local_mat = rec.raw_matrix.copy()
            local_mat.transpose()

            # Se parent == [root], ruotiamo di 90° su X
            if rec.parent and rec.parent.name == "[root]":
                conversion_90_x = mathutils.Matrix([
                    [1, 0, 0, 0],
                    [0, 0, -1, 0],
                    [0, 1, 0, 0],
                    [0, 0, 0, 1]
                ])
                local_mat = conversion_90_x @ local_mat
                print(f"   - Node '{rec.name}': +90° su X (parent = [root])")
            else:
                print(f"   - Node '{rec.name}': no rotation (parent != [root])")

            # Assegna la matrix_basis
            rec.blender_object.matrix_basis = local_mat

    def print_final_hierarchy(self):
        """
        @fn print_final_hierarchy(self)
        @brief Stampa la gerarchia di nodi ricostruita, per debug.
        """
        print("[OVOImporter.print_final_hierarchy] Inizio stampa.\n")
        top_nodes = [r for r in self.parsed_nodes if r.parent is None]

        def _print_rec(rr, indent=0):
            print("  " * indent + f"+ {rr.name} ({rr.node_type})")
            for child in self.parsed_nodes:
                if child.parent == rr:
                    _print_rec(child, indent+1)

        for tnode in top_nodes:
            _print_rec(tnode)
        print("\n[OVOImporter.print_final_hierarchy] Fine stampa.")


    # ----------------------------------------------------------------------
    #   Funzioni di parse "raw" (senza rotazione) per node, mesh, light
    # ----------------------------------------------------------------------

    def parse_node_basic_raw(self, chunk_data):
        """
        @fn parse_node_basic_raw(self, chunk_data)
        @brief Legge un chunk di tipo NODE (ID=1), estrae il nome, la matrice e il children_count.
        @param chunk_data Byte array del chunk.
        @return (node_name, raw_matrix, children_count).
        """
        file_obj = io.BytesIO(chunk_data)
        node_name = OVOScene._read_string(file_obj)

        matrix_bytes = file_obj.read(64)
        matrix_values = struct.unpack("<16f", matrix_bytes)
        raw_matrix = mathutils.Matrix([matrix_values[i:i+4] for i in range(0,16,4)])

        children_count = struct.unpack("<I", file_obj.read(4))[0]
        _target_node = OVOScene._read_string(file_obj)

        print(f"[parse_node_basic_raw] name={node_name}, children={children_count}")
        return node_name, raw_matrix, children_count

    def parse_mesh_raw(self, chunk_data):
        file = io.BytesIO(chunk_data)
        mesh_name = OVOScene._read_string(file)

        matrix_bytes = file.read(64)
        matrix_values = struct.unpack('16f', matrix_bytes)
        raw_matrix = mathutils.Matrix([matrix_values[i:i + 4] for i in range(0, 16, 4)])

        children_count = struct.unpack('I', file.read(4))[0]
        _target = OVOScene._read_string(file)
        mesh_subtype = struct.unpack('B', file.read(1))[0]
        material_name = OVOScene._read_string(file)

        print(f"[parse_mesh_raw] Mesh='{mesh_name}', child={children_count}, mat='{material_name}'")

        # Bounding sphere + minBox + maxBox
        file.seek(4 + 12 + 12, 1)

        # Parsing dei dati di fisica
        physics_flag = struct.unpack('B', file.read(1))[0]
        physics_data = OVOMesh._read_physics_data(file) if physics_flag else None

        lod_count = struct.unpack('I', file.read(4))[0]
        if lod_count == 0:
            print(f"[WARNING] Mesh '{mesh_name}' ha 0 LOD! Creando una mesh di fallback.")
            mesh_data = bpy.data.meshes.new(mesh_name)
            obj = bpy.data.objects.new(mesh_name, mesh_data)
            return mesh_name, raw_matrix, children_count, material_name, obj, physics_data

        # LOD0 - Lettura vertici, facce e UV
        vertex_count, face_count = struct.unpack('2I', file.read(8))
        vertices, faces, uvs = [], [], []

        for _ in range(vertex_count):
            pos = struct.unpack('3f', file.read(12))
            _normalData = struct.unpack('I', file.read(4))[0]
            uvData = struct.unpack('I', file.read(4))[0]
            _tangent = file.read(4)

            vertices.append(pos)
            uv = decode_half2x16(uvData)
            uvs.append(uv)

        for _ in range(face_count):
            face = struct.unpack('3I', file.read(12))
            faces.append(face)

        # Controllo che ci siano effettivamente vertici e facce
        if len(vertices) == 0 or len(faces) == 0:
            print(f"[ERROR] Mesh '{mesh_name}' non ha vertici o facce validi!")
            return mesh_name, raw_matrix, children_count, material_name, None, physics_data

        # Creazione della mesh in Blender
        mesh_data = bpy.data.meshes.new(mesh_name)
        mesh_data.from_pydata(vertices, [], faces)
        mesh_data.update()

        # Creazione UV Map
        if len(uvs) == vertex_count:
            uv_layer = mesh_data.uv_layers.new(name="UVMap")
            for poly in mesh_data.polygons:
                for loop_idx in range(poly.loop_start, poly.loop_start + poly.loop_total):
                    vert_idx = mesh_data.loops[loop_idx].vertex_index
                    uv_layer.data[loop_idx].uv = uvs[vert_idx]

        mesh_obj = bpy.data.objects.new(mesh_name, mesh_data)
        print(f"[parse_mesh_raw] Creato obj '{mesh_name}' con {vertex_count} vert e {face_count} facce.")

        return mesh_name, raw_matrix, children_count, material_name, mesh_obj, physics_data

    def parse_light_raw(self, chunk_data):
        """
        @fn parse_light_raw(self, chunk_data)
        @brief Legge un chunk di tipo LIGHT (ID=16), crea l'oggetto Light in Blender.
        @param chunk_data Byte array del chunk.
        @return (light_name, raw_matrix, children_count, light_data).
        """
        file = io.BytesIO(chunk_data)
        name = OVOScene._read_string(file)
        matrix_bytes = file.read(64)
        matrix_values = struct.unpack("<16f", matrix_bytes)
        raw_matrix = mathutils.Matrix([matrix_values[i:i+4] for i in range(0,16,4)])
        child_count = struct.unpack("<I", file.read(4))[0]
        _ = OVOScene._read_string(file)
        light_type = struct.unpack("<B", file.read(1))[0]
        color = struct.unpack("<3f", file.read(12))
        radius = struct.unpack("<f", file.read(4))[0]
        direction = struct.unpack("<3f", file.read(12))
        cutoff = struct.unpack("<f", file.read(4))[0]
        spot_exponent = struct.unpack("<f", file.read(4))[0]
        shadow = struct.unpack("<B", file.read(1))[0]
        volumetric = struct.unpack("<B", file.read(1))[0]

        ldata = OVOLight._create_blender_light_data(name, light_type, color, radius,
                                                    cutoff, spot_exponent, shadow)
        return name, raw_matrix, child_count, ldata

# ====================================
#  OVOMesh (Updated with Physics)
# ====================================
class OVOMesh:
    """
    @class OVOMesh
    @brief Rappresenta una mesh OVO con dati di vertici, UV e proprietà fisiche.
    """
    @staticmethod
    def _read_physics_data(file_obj):
        """
        @fn _read_physics_data(file_obj)
        @brief Legge i dati fisici della mesh.
        @return Dizionario contenente i dati fisici.
        """
        print("    [OVOMesh._read_physics_data] Lettura dati fisici.")
        start_pos = file_obj.tell()

        type_ = struct.unpack('B', file_obj.read(1))[0]  # Tipo di corpo rigido
        file_obj.seek(3, 1)  # Ignoriamo collisioni e altri flag

        hull_type = struct.unpack('B', file_obj.read(1))[0]  # Tipo di collisione
        mass_center = struct.unpack('<3f', file_obj.read(12))  # Centro di massa
        mass, static_fric, dyn_fric, bounciness, lin_damp, ang_damp = struct.unpack('<6f', file_obj.read(24))
        nr_hulls, _pad = struct.unpack('<II', file_obj.read(8))  # Numero di hull custom (ignorati per ora)

        end_pos = file_obj.tell()
        print(f"    [OVOMesh._read_physics_data] Bytes letti: {end_pos - start_pos}")

        return {
            "type": type_,
            "hullType": hull_type,
            "mass": mass,
            "staticFriction": static_fric,
            "dynamicFriction": dyn_fric,
            "bounciness": bounciness,
            "linearDamping": lin_damp,
            "angularDamping": ang_damp,
        }

    @staticmethod
    def apply_physics_to_object(obj, phys_data):
        print(f"    [OVOMesh] Applying physics to '{obj.name}'")

        if obj.type != 'MESH':
            print(f"    [WARNING] Object '{obj.name}' is not a mesh! Assigning a blank mesh.")
            mesh_data = bpy.data.meshes.new(obj.name)
            obj.data = mesh_data

        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        bpy.ops.rigidbody.object_add(type='ACTIVE')

        rb = obj.rigid_body
        rb.type = 'ACTIVE' if phys_data["type"] == 1 else 'PASSIVE'

        hull_map = {1: 'SPHERE', 2: 'BOX', 3: 'CAPSULE', 4: 'CONVEX_HULL', 7: 'MESH'}
        rb.collision_shape = hull_map.get(phys_data["hullType"], 'BOX')

        rb.mass = phys_data["mass"]
        rb.friction = phys_data["dynamicFriction"]
        rb.restitution = phys_data["bounciness"]
        rb.linear_damping = phys_data["linearDamping"]
        rb.angular_damping = phys_data["angularDamping"]

        # ✅ Force visibility in viewport
        obj.hide_set(False)  # Ensure object is visible
        obj.hide_viewport = False  # Ensure it is rendered in viewport
        obj.display_type = 'TEXTURED'  # Ensure it appears as a solid mesh
        obj.show_wire = False  # Disable wireframe overlay

        obj.select_set(False)

# ====================================
#  OVOMaterial
# ====================================
class OVOMaterial:
    """
    @class OVOMaterial
    @brief Rappresenta un materiale OVO con parametri base e possibili texture (albedo, normal, ecc.).
    """
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
        """
        @fn parse_material(chunk_data)
        @brief Legge i dati di un Material (ID=9) dal file OVO.
        @param chunk_data Byte array del chunk.
        @return Un oggetto OVOMaterial.
        """
        file = io.BytesIO(chunk_data)
        name = OVOScene._read_string(file)
        emissive = struct.unpack("<3f", file.read(12))
        base_color = struct.unpack("<3f", file.read(12))
        roughness = struct.unpack("<f", file.read(4))[0]
        metallic = struct.unpack("<f", file.read(4))[0]
        transparency = struct.unpack("<f", file.read(4))[0]

        ttypes = ["albedo","normal","height","roughness","metalness"]
        textures = {}
        for t in ttypes:
            tname = OVOScene._read_string(file)
            textures[t] = tname if tname != "[none]" else None

        return OVOMaterial(name, base_color, roughness, metallic, transparency, emissive, textures)

    def create_blender_material(self, texdir):
        """
        @fn create_blender_material(self, texdir)
        @brief Crea effettivamente il Material in Blender, assegnando un Principled BSDF e (eventuale) texture.
        @param texdir Directory base dove cercare i file texture (DDS, PNG, ecc.).
        @return Un bpy.types.Material creato.
        """
        mat = bpy.data.materials.new(name=self.name)
        mat.use_nodes = True
        bsdf = None
        for node in mat.node_tree.nodes:
            if node.type == 'BSDF_PRINCIPLED':
                bsdf = node
                break
        if not bsdf:
            print(f"[OVOMaterial] Principled BSDF non trovato in {self.name}")
            self.blender_material = mat
            return mat

        # Imposta parametri PBR
        bsdf.inputs["Base Color"].default_value = (*self.base_color, 1.0)
        bsdf.inputs["Roughness"].default_value = self.roughness
        bsdf.inputs["Metallic"].default_value = self.metallic
        if self.transparency < 1.0:
            mat.blend_method = 'BLEND'
            mat.shadow_method = 'HASHED'
            bsdf.inputs["Alpha"].default_value = self.transparency
        if "Emission" in bsdf.inputs:
            bsdf.inputs["Emission"].default_value = (*self.emissive,1.0)

        # Se c'è una texture albedo, proviamo a caricarla
        albedo_tex = self.textures.get("albedo")
        if albedo_tex and albedo_tex != "[none]":
            texture_path = os.path.join(texdir, albedo_tex)
            if os.path.isfile(texture_path):
                try:
                    img = bpy.data.images.load(texture_path)
                    tex_node = mat.node_tree.nodes.new('ShaderNodeTexImage')
                    tex_node.image = img
                    tex_node.label = "Albedo Texture"
                    # Collega l'uscita Color al Base Color
                    mat.node_tree.links.new(tex_node.outputs["Color"], bsdf.inputs["Base Color"])
                except Exception as ex:
                    print(f"[OVOMaterial] Errore caricando '{texture_path}': {ex}")
            else:
                print(f"[OVOMaterial] File texture non trovato: {texture_path}")

        self.blender_material = mat
        return mat


# ====================================
#  OVOLight
# ====================================
class OVOLight:
    """
    @class OVOLight
    @brief Funzioni ausiliarie per creare un oggetto Light in Blender, in base ai parametri OVO.
    """
    @staticmethod
    def _create_blender_light_data(name, ltype, color, radius, cutoff, sp_exponent, shadow):
        """
        @fn _create_blender_light_data(...)
        @brief Crea un bpy.types.Light configurato come Omni, Sun o Spot.
        """
        if ltype == 0:  # point
            ldata = bpy.data.lights.new(name=name, type='POINT')
            ldata.color = color
            ldata.energy = radius * 10
            ldata.use_shadow = bool(shadow)
            return ldata
        elif ltype == 1: # sun
            ldata = bpy.data.lights.new(name=name, type='SUN')
            ldata.color = color
            ldata.energy = radius * 10
            ldata.use_shadow = bool(shadow)
            return ldata
        elif ltype == 2: # spot
            ldata = bpy.data.lights.new(name=name, type='SPOT')
            ldata.color = color
            ldata.energy = radius * 10
            ldata.spot_size = cutoff
            ldata.spot_blend = sp_exponent / 10.0
            ldata.use_shadow = bool(shadow)
            return ldata
        else:
            # fallback point
            ldata = bpy.data.lights.new(name=name, type='POINT')
            return ldata

# ====================================
#  OVOScene
# ====================================
class OVOScene:
    """
    @class OVOScene
    @brief Classe contenente funzioni di utilità statiche per la lettura di stringhe dal file OVO.
    """
    @staticmethod
    def _read_string(file):
        """
        @fn _read_string(file)
        @brief Legge una stringa terminata da '\\x00' da un file binario.
        @param file Oggetto file.
        @return Una stringa in Python (UTF-8).
        """
        chars = []
        while True:
            c = file.read(1)
            if c == b'\x00' or not c:
                break
            chars.append(c)
        return b''.join(chars).decode('utf-8', errors='replace')


# ====================================
#  Blender Import Operator
# ====================================
class OT_ImportOVO(Operator, ImportHelper):
    """
    @class OT_ImportOVO
    @brief Operatore Blender che gestisce l'import di file OVO, apparendo in 'File > Import'.
    """
    bl_idname = "import_scene.ovo"
    bl_label = "Import OVO"
    filename_ext = ".ovo"
    filter_glob: StringProperty(default="*.ovo", options={'HIDDEN'})

    def execute(self, context):
        """
        @fn execute(self, context)
        @brief Invocato quando l'utente importa un file .ovo da Blender.
        """
        importer = OVOImporter(self.filepath)
        res = importer.import_scene()
        bpy.context.view_layer.update()
        return res


def menu_func_import(self, context):
    """
    @fn menu_func_import(self, context)
    @brief Aggiunge l'operatore OT_ImportOVO nel menu 'File > Import'.
    """
    self.layout.operator(OT_ImportOVO.bl_idname, text="OverVision Object (.ovo)")


def register():
    """
    @fn register()
    @brief Registra la classe OT_ImportOVO in Blender e aggiunge la voce al menu import.
    """
    bpy.utils.register_class(OT_ImportOVO)
    bpy.types.TOPBAR_MT_file_import.append(menu_func_import)


def unregister():
    """
    @fn unregister()
    @brief Deregistra l'addon rimuovendo l'operatore dal menu import.
    """
    bpy.types.TOPBAR_MT_file_import.remove(menu_func_import)
    bpy.utils.unregister_class(OT_ImportOVO)


if __name__ == "__main__":
    register()
