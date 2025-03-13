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
#  OVOMesh (gestisce i dati fisici)
# ====================================
class OVOMesh:
    """
    @class OVOMesh
    @brief Racchiude funzioni ausiliarie per la parte fisica delle mesh OVO.
    """
    @staticmethod
    def _read_physics_data(file_obj):
        start_pos = file_obj.tell()

        # 1 byte: type_
        type_ = struct.unpack('B', file_obj.read(1))[0]

        print(f'[Object_Type] value: {type_}')

        # 1 byte: contCollision
        cont_collision = struct.unpack('B', file_obj.read(1))[0]

        print(f'[Cont_Collision] value: {cont_collision}')

        # 1 byte: collideWithRB
        collide_with_rb = struct.unpack('B', file_obj.read(1))[0]

        print(f'[Collide_With_RB] value: {collide_with_rb}')

        # 1 byte: hull_type
        hull_type = struct.unpack('B', file_obj.read(1))[0]

        print(f'[Hull_Type] value: {hull_type}')

        # 12 byte: massCenter
        mass_center = struct.unpack('<3f', file_obj.read(12))

        print(f'[Mass_Center] value: {mass_center}')

        # 24 byte: mass, staticFric, dynFric, bounciness, linDamp, angDamp
        mass, static_fric, dyn_fric, bounciness, lin_damp, ang_damp = struct.unpack('<6f', file_obj.read(24))

        # 4 byte: nr_hulls
        nr_hulls = struct.unpack('<I', file_obj.read(4))[0]

        print(f'[Nr_Hulls] value: {nr_hulls}')

        # 4 byte: padding
        _pad = struct.unpack('<I', file_obj.read(4))[0]

        # 8 + 8 byte: due puntatori riservati (sempre zero, ma vanno letti)
        reserved1, reserved2 = struct.unpack('<QQ', file_obj.read(16))

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
        """
        @fn apply_physics_to_object(obj, phys_data)
        @brief Applica i parametri di fisica a un oggetto Blender (Rigid Body).
        """
        if not obj or obj.type != 'MESH':
            print(f"    [OVOMesh.apply_physics_to_object] WARNING: '{obj.name}' non è una mesh.")
            return

        if not obj.users_collection:
            print(f"    [OVOMesh.apply_physics_to_object] '{obj.name}' non ha collezioni, lo linko ora.")
            bpy.context.collection.objects.link(obj)

        print(f"    [OVOMesh] Assegno fisica a '{obj.name}' con parametri={phys_data}")
        bpy.ops.object.select_all(action='DESELECT')
        bpy.context.view_layer.objects.active = obj
        obj.select_set(True)

        # Aggiungiamo il rigid body come 'ACTIVE'
        bpy.ops.rigidbody.object_add(type='ACTIVE')
        rb = obj.rigid_body

        if phys_data["type"] == 1:  # Dynamic
            rb.type = 'ACTIVE'
        elif phys_data["type"] == 3:  # Static
            rb.type = 'PASSIVE'
        else:
            rb.type = 'ACTIVE'

        hull_map = {
            1: 'SPHERE',
            2: 'BOX',
            3: 'CAPSULE',
            4: 'CONVEX_HULL'
        }
        rb.collision_shape = hull_map.get(phys_data["hullType"], 'BOX')

        rb.mass = phys_data["mass"]
        rb.friction = phys_data["dynamicFriction"]
        rb.restitution = phys_data["bounciness"]
        rb.linear_damping = phys_data["linearDamping"]
        rb.angular_damping = phys_data["angularDamping"]

        obj.display_type = 'TEXTURED'
        obj.hide_viewport = False

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

        ttypes = ["albedo", "normal", "height", "roughness", "metalness"]
        textures = {}
        for t in ttypes:
            t_name = OVOScene._read_string(file)
            textures[t] = t_name if t_name != "[none]" else None

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

        if bsdf is None:
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
            bsdf.inputs["Emission"].default_value = (*self.emissive, 1.0)

        # Se c'è una texture albedo, la carichiamo
        albedo_tex = self.textures.get("albedo")
        if albedo_tex and albedo_tex != "[none]":
            texture_path = os.path.join(texdir, albedo_tex)
            if os.path.isfile(texture_path):
                try:
                    img = bpy.data.images.load(texture_path)
                    tex_node = mat.node_tree.nodes.new('ShaderNodeTexImage')
                    tex_node.image = img
                    tex_node.label = "Albedo Texture"
                    mat.node_tree.links.new(tex_node.outputs["Color"], bsdf.inputs["Base Color"])
                except Exception as ex:
                    print(f"[OVOMaterial] Errore caricando '{texture_path}': {ex}")
            else:
                print(f"[OVOMaterial] Texture '{albedo_tex}' non trovata in {texdir}")

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
        if ltype == 0:  # OMNI
            ldata = bpy.data.lights.new(name=name, type='POINT')
            ldata.color = color
            ldata.energy = radius * 10
            ldata.use_shadow = bool(shadow)
            return ldata
        elif ltype == 1:  # DIRECTIONAL
            ldata = bpy.data.lights.new(name=name, type='SUN')
            ldata.color = color
            ldata.energy = radius * 10
            ldata.use_shadow = bool(shadow)
            return ldata
        elif ltype == 2:  # SPOT
            ldata = bpy.data.lights.new(name=name, type='SPOT')
            ldata.color = color
            ldata.energy = radius * 10
            ldata.spot_size = cutoff
            ldata.spot_blend = sp_exponent / 10.0
            ldata.use_shadow = bool(shadow)
            return ldata
        else:
            # fallback
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
#  OVOImporter
# ====================================
class OVOImporter:
    """
    @class OVOImporter
    @brief Classe principale che gestisce il parsing di un file OVO e l'import in Blender.
    """
    def __init__(self, filepath):
        """
        @fn __init__(self, filepath)
        @brief Inizializza l'importer con un percorso al file .ovo.
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
        @brief Flusso principale di import. Legge il file, crea nodi/luci/mesh e costruisce la gerarchia.
        """
        print(f"[OVOImporter.import_scene] Inizio import: {self.filepath}")
        if not self.read_ovo_file():
            return {'CANCELLED'}

        self.parse_chunks()
        self.build_hierarchy_stack_approach()
        self.establish_root_node()
        self.apply_matrices_with_partial_rotation()

        print("[OVOImporter.import_scene] Gerarchia finale importata:")
        self.print_final_hierarchy()
        return {'FINISHED'}

    def parse_chunks(self):
        """
        @fn parse_chunks(self)
        @brief Scorre i chunk e crea materiali, nodi, luci, mesh (con fisica).
        """
        print("[OVOImporter.parse_chunks] Inizio analisi chunk.")
        for i, chunk in enumerate(self.chunks):
            cid = chunk.chunk_id
            print(f"  > Chunk #{i}, ID={cid}, size={chunk.chunk_size}")

            if cid == 9:  # MATERIAL
                material = OVOMaterial.parse_material(chunk.data)
                mat = material.create_blender_material(self.texture_directory)
                self.materials[material.name] = material
                print(f"    [INFO] Creato Material '{material.name}'")
                continue

            if cid == 1:  # NODE
                node_name, raw_matrix, children = self.parse_node_basic_raw(chunk.data)
                node_obj = bpy.data.objects.new(node_name, None)
                bpy.context.collection.objects.link(node_obj)  # Always link every node
                node_obj.matrix_world = mathutils.Matrix.Identity(4)
                node_obj.empty_display_type = 'PLAIN_AXES'
                node_obj.empty_display_size = 1.0
                rec = NodeRecord(node_name, "NODE", children, node_obj, raw_matrix)
                self.parsed_nodes.append(rec)
                print(f"    [INFO] Creato NodeRecord: {rec}")
                continue

            if cid == 16:  # LIGHT
                light_name, raw_matrix, children, light_data = self.parse_light_raw(chunk.data)
                light_obj = bpy.data.objects.new(light_name, light_data)
                bpy.context.collection.objects.link(light_obj)
                light_obj.matrix_world = mathutils.Matrix.Identity(4)
                rec = NodeRecord(light_name, "LIGHT", children, light_obj, raw_matrix)
                self.parsed_nodes.append(rec)
                print(f"    [INFO] Creato Light NodeRecord: {rec}")
                continue

            if cid == 18:  # MESH
                mesh_name, raw_matrix, children, mat_name, mesh_obj, phys_data = self.parse_mesh_raw(chunk.data)

                if mat_name in self.materials:
                    mat = self.materials[mat_name].blender_material
                    if mat:
                        if not mesh_obj.data.materials:
                            mesh_obj.data.materials.append(mat)
                        else:
                            mesh_obj.data.materials[0] = mat

                # MESH: Link to the active collection
                if not bpy.context.collection.objects.get(mesh_obj.name):
                    bpy.context.collection.objects.link(mesh_obj)

                mesh_obj.matrix_world = mathutils.Matrix.Identity(4)

                if phys_data:
                    OVOMesh.apply_physics_to_object(mesh_obj, phys_data)

                rec = NodeRecord(mesh_name, "MESH", children, mesh_obj, raw_matrix)
                self.parsed_nodes.append(rec)
                print(f"    [INFO] Creato Mesh NodeRecord: {rec}")
                continue

            print(f"    [WARNING] Chunk ID={cid} non gestito.")
        print("[OVOImporter.parse_chunks] Fine analisi chunk.")

    def build_hierarchy_stack_approach(self):
        """
        @fn build_hierarchy_stack_approach
        @brief Ricostruisce la gerarchia parent-child con uno stack, come da struttura OVO.
        """
        print("[OVOImporter.build_hierarchy_stack_approach] Inizio.")
        stack = []
        for i, record in enumerate(self.parsed_nodes):
            while stack and stack[-1].children_count == 0:
                popped = stack.pop()
                print(f"      [STACK] Rimosso: {popped}")

            if stack:
                parent = stack[-1]
                record.parent = parent
                parent.children_count -= 1
                print(f"      [HIER] '{record.name}' figlio di '{parent.name}'")

            if record.children_count > 0:
                stack.append(record)

        print("[OVOImporter.build_hierarchy_stack_approach] Impostazione parent in Blender.")
        for rec in self.parsed_nodes:
            if rec.parent:
                rec.blender_object.parent = rec.parent.blender_object
                rec.blender_object.matrix_parent_inverse = rec.parent.blender_object.matrix_world.inverted()
                print(f"      [BLENDER] '{rec.name}' -> parent='{rec.parent.name}'")

    def establish_root_node(self):
        """
        @fn establish_root_node
        @brief Se manca [root] e c'è più di un toplevel, crea un root fittizio.
        """
        print("[OVOImporter.establish_root_node] Check root esistente.")
        root_found = any(r.name == "[root]" for r in self.parsed_nodes)
        if root_found:
            print("[INFO] [root] esiste già.")
            return

        toplevel = [r for r in self.parsed_nodes if r.parent is None]
        if len(toplevel) > 1:
            print(f"[INFO] Creo root fittizio, toplevel={len(toplevel)}.")
            root_obj = bpy.data.objects.new("[root]", None)
            bpy.context.collection.objects.link(root_obj)
            for r in toplevel:
                r.blender_object.parent = root_obj
                r.blender_object.matrix_parent_inverse = root_obj.matrix_world.inverted()
                r.parent = None

    def apply_matrices_with_partial_rotation(self):
        """
        @fn apply_matrices_with_partial_rotation
        @brief Fa la trasposizione + rotazione di 90° su X per i figli diretti di [root].
        """
        print("[OVOImporter] apply_matrices_with_partial_rotation.")
        for rec in self.parsed_nodes:
            if rec.name == "[root]":
                print("   - skip [root]")
                continue
            mat = rec.raw_matrix.copy()
            mat.transpose()

            if rec.parent and rec.parent.name == "[root]":
                # Ruota di 90° su X
                conv_90_x = mathutils.Matrix([
                    [1, 0, 0, 0],
                    [0, 0, -1, 0],
                    [0, 1, 0, 0],
                    [0, 0, 0, 1]
                ])
                mat = conv_90_x @ mat
                print(f"   - Node '{rec.name}' => +90° su X (parent=[root])")

            rec.blender_object.matrix_basis = mat

    def print_final_hierarchy(self):
        """
        @fn print_final_hierarchy
        @brief Stampa la gerarchia resultante.
        """
        print("[OVOImporter.print_final_hierarchy]")

        top_nodes = [r for r in self.parsed_nodes if r.parent is None]
        def _rec_print(nodo, indent=0):
            print("  " * indent + f"+ {nodo.name} ({nodo.node_type})")
            for child in self.parsed_nodes:
                if child.parent == nodo:
                    _rec_print(child, indent+1)

        for top in top_nodes:
            _rec_print(top)

    # ---------------------------------------------------------------
    # Parse "raw" functions for Node, Mesh, Light
    # ---------------------------------------------------------------
    def parse_node_basic_raw(self, chunk_data):
        """
        @fn parse_node_basic_raw
        @brief Legge chunk ID=1 (NODE).
        """
        file_obj = io.BytesIO(chunk_data)
        node_name = OVOScene._read_string(file_obj)

        matrix_bytes = file_obj.read(64)
        matrix_vals = struct.unpack("<16f", matrix_bytes)
        raw_matrix = mathutils.Matrix([matrix_vals[i:i+4] for i in range(0,16,4)])

        children = struct.unpack("<I", file_obj.read(4))[0]
        _target = OVOScene._read_string(file_obj)

        print(f"[parse_node_basic_raw] name={node_name}, children={children}")
        return node_name, raw_matrix, children

    def parse_mesh_raw(self, chunk_data):
        """
        @fn parse_mesh_raw(self, chunk_data)
        @brief Legge chunk ID=18 (MESH), inclusa la sezione fisica e LOD0 con UV.
               Ora legge tutti i dati e solo dopo crea l'oggetto Blender e
               applica le proprietà fisiche. Evita problemi di ordine/interpretazione.

        @param chunk_data I byte del chunk relativo a una mesh.
        @return (mesh_name, raw_matrix, children_count, material_name, mesh_obj, physics_data)
        """
        file = io.BytesIO(chunk_data)

        # ---- Lettura dati base mesh ----
        mesh_name = OVOScene._read_string(file)
        print(f"[parse_mesh_raw] *** Inizio parsing mesh '{mesh_name}' ***")

        # 4x4 matrix in row-major
        mbytes = file.read(64)
        mvals = struct.unpack('<16f', mbytes)
        raw_matrix = mathutils.Matrix([mvals[i:i + 4] for i in range(0, 16, 4)])
        print(f"[parse_mesh_raw] Matrix read (row-major, transposed in Blender successivamente):\n  {raw_matrix}")

        children = struct.unpack("<I", file.read(4))[0]
        _target = OVOScene._read_string(file)
        print(f"[parse_mesh_raw] children={children}, target={_target}")

        # Legge il subtype (OvMesh::Subtype)
        mesh_subtype = struct.unpack('B', file.read(1))[0]
        material_name = OVOScene._read_string(file)
        print(f"[parse_mesh_raw] mesh_subtype={mesh_subtype}, material_name={material_name}")

        # Leggi bounding sphere + minBox + maxBox (4 + 12 + 12 byte)
        bsphere = struct.unpack('<f', file.read(4))[0]
        min_box = struct.unpack('<3f', file.read(12))
        max_box = struct.unpack('<3f', file.read(12))
        print(f"[parse_mesh_raw] boundingSphere={bsphere}, minBox={min_box}, maxBox={max_box}")

        # Lettura dati fisica
        physics_flag = struct.unpack('B', file.read(1))[0]
        physics_data = None
        if physics_flag:
            physics_data = OVOMesh._read_physics_data(file)
            print(f"[parse_mesh_raw] physics_data={physics_data}")
        else:
            print("[parse_mesh_raw] Nessun dato fisico presente.")

        # Lettura LOD e geometria
        lod_count = struct.unpack('I', file.read(4))[0]
        print(f"[parse_mesh_raw] LOD count={lod_count}")
        if lod_count == 0:
            # Mesh vuota
            fallback_mesh = bpy.data.meshes.new(mesh_name)
            mesh_obj = bpy.data.objects.new(mesh_name, fallback_mesh)
            print("[parse_mesh_raw] LOD=0 => Mesh vuota creata.")
            return mesh_name, raw_matrix, children, material_name, mesh_obj, physics_data

        vertex_count, face_count = struct.unpack('2I', file.read(8))

        # Liste per accumulare i dati geometrici
        vertices = []
        faces = []
        uvs = []

        # Lettura vertici
        for idx in range(vertex_count):
            pos = struct.unpack('<3f', file.read(12))
            normalData = struct.unpack('<I', file.read(4))[0]
            uvData = struct.unpack('<I', file.read(4))[0]
            tangentData = file.read(4)
            vertices.append(pos)
            # decode uv
            uv = decode_half2x16(uvData)
            uvs.append(uv)
            # Log facoltativo su un subset di vertici per non esagerare
            if idx < 5:
                print(f"   [parse_mesh_raw] Vtx#{idx} => pos={pos}, normalPacked={normalData}, uv={uv}")

        # Lettura facce
        for fidx in range(face_count):
            f = struct.unpack('<3I', file.read(12))
            faces.append(f)
            if fidx < 5:
                print(f"   [parse_mesh_raw] Face#{fidx} => indices={f}")

        # Creazione e popolamento Mesh Blender
        mesh_data = bpy.data.meshes.new(mesh_name)
        mesh_data.from_pydata(vertices, [], faces)
        mesh_data.update()
        print(
            f"[parse_mesh_raw] Creata mesh_data '{mesh_name}' con {len(mesh_data.vertices)} vertici Blender e {len(mesh_data.polygons)} poligoni Blender.")

        # Se ci sono UV, li copiamo
        if len(uvs) == vertex_count and vertex_count > 0:
            uv_layer = mesh_data.uv_layers.new(name="UVMap")
            for poly in mesh_data.polygons:
                for loop_idx in range(poly.loop_start, poly.loop_start + poly.loop_total):
                    vert_idx = mesh_data.loops[loop_idx].vertex_index
                    uv_layer.data[loop_idx].uv = uvs[vert_idx]
            print("[parse_mesh_raw] UV map 'UVMap' creato e assegnato con successo.")

        # Creiamo l'oggetto Blender collegato alla mesh
        mesh_obj = bpy.data.objects.new(mesh_name, mesh_data)
        print(f"[parse_mesh_raw] mesh_obj='{mesh_obj.name}' creato.")

        # Se esiste il materiale, lo assegnamo
        if material_name in self.materials:
            mat = self.materials[material_name].blender_material
            if mat:
                if not mesh_obj.data.materials:
                    mesh_obj.data.materials.append(mat)
                else:
                    mesh_obj.data.materials[0] = mat
                print(f"[parse_mesh_raw] Assegnato materiale '{mat.name}' a '{mesh_obj.name}'")
        else:
            print("[parse_mesh_raw] Nessun materiale da assegnare o materiale non trovato nella libreria.")

        # ---- Applica i dati di fisica, se presenti ----
        if physics_data:
            print(f"[parse_mesh_raw] Applico i dati fisici a '{mesh_obj.name}'...")
            OVOMesh.apply_physics_to_object(mesh_obj, physics_data)
        else:
            print("[parse_mesh_raw] Nessun rigid body applicato (physics_data assente).")

        print(f"[parse_mesh_raw] *** Fine parsing mesh '{mesh_name}' ***\n")
        return mesh_name, raw_matrix, children, material_name, mesh_obj, physics_data

    def parse_light_raw(self, chunk_data):
        """
        @fn parse_light_raw
        @brief Legge chunk ID=16 (LIGHT).
        """
        file = io.BytesIO(chunk_data)
        light_name = OVOScene._read_string(file)

        mat_bytes = file.read(64)
        mat_vals = struct.unpack('<16f', mat_bytes)
        raw_matrix = mathutils.Matrix([mat_vals[i:i+4] for i in range(0,16,4)])

        children = struct.unpack('<I', file.read(4))[0]
        _target = OVOScene._read_string(file)

        light_type = struct.unpack('<B', file.read(1))[0]
        color = struct.unpack('<3f', file.read(12))
        radius = struct.unpack('<f', file.read(4))[0]
        direction = struct.unpack('<3f', file.read(12))
        cutoff = struct.unpack('<f', file.read(4))[0]
        spot_exp = struct.unpack('<f', file.read(4))[0]
        shadow = struct.unpack('<B', file.read(1))[0]
        volumetric = struct.unpack('<B', file.read(1))[0]

        ldata = OVOLight._create_blender_light_data(light_name, light_type, color, radius,
                                                    cutoff, spot_exp, shadow)

        # Compute the rotation
        default_dir = mathutils.Vector((0, 0, -1))
        target_dir = mathutils.Vector(direction).normalized()
        rot_quat = default_dir.rotation_difference(target_dir)

        
        print(f"[parse_light_raw] Light='{light_name}', children={children}, type={light_type}")
        return light_name, raw_matrix, children, ldata

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
        importer = OVOImporter(self.filepath)
        result = importer.import_scene()
        bpy.context.view_layer.update()
        return result


def menu_func_import(self, context):
    """
    @fn menu_func_import(self, context)
    @brief Aggiunge l'operatore OT_ImportOVO nel menu 'File > Import'.
    """
    self.layout.operator(OT_ImportOVO.bl_idname, text="OverVision Object (.ovo)")


def register():
    bpy.utils.register_class(OT_ImportOVO)
    bpy.types.TOPBAR_MT_file_import.append(menu_func_import)


def unregister():
    bpy.types.TOPBAR_MT_file_import.remove(menu_func_import)
    bpy.utils.unregister_class(OT_ImportOVO)


if __name__ == "__main__":
    register()