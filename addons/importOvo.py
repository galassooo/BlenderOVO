# ===================================
#   Blender Addon Information
# ===================================
bl_info = {
    "name": "OVO Format Importer",
    "author": "Martina",
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

# ===================================
#   Node Information Storage
# ===================================
class NodeRecord:
    """
    Struttura di appoggio per tenere traccia di:
    - Nome del nodo
    - Tipo ("NODE", "MESH", "LIGHT")
    - Numero di figli attesi (children_count)
    - Oggetto Blender già creato (blender_object)
    """
    def __init__(self, name, node_type, children_count, blender_object):
        self.name = name
        self.node_type = node_type  # "NODE", "MESH" o "LIGHT"
        self.children_count = children_count
        self.blender_object = blender_object
        self.parent = None


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
        """
        Legge 8 byte (ID e size) e poi i successivi chunk_size byte come 'data'.
        Restituisce None se siamo a fine file.
        """
        header = file.read(8)
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
    Classe principale che si occupa del caricamento del file OVO,
    della creazione di materiali/nodi/luci/mesh in Blender e
    della costruzione della gerarchia.
    """

    def __init__(self, filepath):
        self.filepath = filepath
        self.chunks = []
        self.materials = {}
        self.texture_directory = os.path.dirname(filepath)
        self.scene = None

        # Elenco (in ordine di lettura) dei nodi/mesh/light: NodeRecord
        self.parsed_nodes = []

    def read_ovo_file(self):
        """Legge tutti i chunk dal file e li memorizza in self.chunks."""
        with open(self.filepath, "rb") as file:
            while True:
                chunk = OVOChunk.read_chunk(file)
                if chunk is None:
                    break
                self.chunks.append(chunk)

        print(f"[INFO] Lettura completata di {len(self.chunks)} chunk.")
        return True

    def import_scene(self):
        """Funzione principale di import. Restituisce {'FINISHED'} o {'CANCELLED'}."""
        if not self.read_ovo_file():
            return {'CANCELLED'}

        # 1) Analizza i chunk e crea materiali + strutture di appoggio
        self.parse_chunks()

        # 2) Costruisce la gerarchia basandosi sullo stack (ordine di lettura)
        self.build_hierarchy_stack_approach()

        # 3) Crea (o individua) un root fittizio se necessario
        self.establish_root_node()

        print("\n[FINAL HIERARCHY]")
        self.print_final_hierarchy()

        return {'FINISHED'}

    def parse_chunks(self):
        """
        Esegue un'unica passata su self.chunks nell'ordine in cui sono stati letti:
        - Se chunk è material (ID=9), parse e crea blender material
        - Se chunk è node (ID=1) => parse e crea OVONode + NodeRecord
        - Se chunk è light (ID=16) => parse e crea OVOLight + NodeRecord
        - Se chunk è mesh (ID=18) => parse e crea OVOMesh + NodeRecord
        - Altri chunk ignorati
        """
        for chunk in self.chunks:
            cid = chunk.chunk_id

            # --- Materiali (chunk ID 9) ---
            if cid == 9:
                material = OVOMaterial.parse_material(chunk.data)
                mat = material.create_blender_material(self.texture_directory)
                self.materials[material.name] = material
                continue

            # --- Node generico (chunk ID 1) ---
            if cid == 1:
                node_name, matrix, children_count = self.parse_node_basic(chunk.data)
                node_obj = bpy.data.objects.new(node_name, None)
                bpy.context.collection.objects.link(node_obj)

                # Assegno la trasformazione (già convertita)
                node_obj.matrix_world = matrix

                record = NodeRecord(name=node_name,
                                    node_type="NODE",
                                    children_count=children_count,
                                    blender_object=node_obj)
                self.parsed_nodes.append(record)
                continue

            # --- Light (chunk ID 16) ---
            if cid == 16:
                light_name, matrix, children_count, light_data = OVOLight.parse_light(chunk.data)
                # Crea la light in Blender
                light_obj = bpy.data.objects.new(light_name, light_data)
                bpy.context.collection.objects.link(light_obj)
                light_obj.matrix_world = matrix

                record = NodeRecord(name=light_name,
                                    node_type="LIGHT",
                                    children_count=children_count,
                                    blender_object=light_obj)
                self.parsed_nodes.append(record)
                continue

            # --- Mesh (chunk ID 18) ---
            if cid == 18:
                (mesh_name, matrix, children_count,
                 material_name, mesh_obj) = OVOMesh.parse_mesh_with_children(chunk.data)

                # Se esiste un materiale omonimo, assegnalo alla mesh
                if material_name in self.materials:
                    mat = self.materials[material_name].blender_material
                    if mat:
                        if not mesh_obj.data.materials:
                            mesh_obj.data.materials.append(mat)
                        else:
                            mesh_obj.data.materials[0] = mat

                mesh_obj.matrix_world = matrix
                bpy.context.collection.objects.link(mesh_obj)

                record = NodeRecord(name=mesh_name,
                                    node_type="MESH",
                                    children_count=children_count,
                                    blender_object=mesh_obj)
                self.parsed_nodes.append(record)
                continue

            # Altri chunk ignorati
            # print(f"[WARNING] Chunk ID={cid} ignorato.")

    def build_hierarchy_stack_approach(self):
        """
        Ricostruisce la gerarchia usando un approccio stack-based,
        in cui i nodi vengono presi nell'ordine di lettura.
        Esempio di logica (simile a OvoReader.cpp):
          - Se lo stack è vuoto, il nodo corrente è "top-level"
          - Altrimenti lo stack.top è il suo genitore.
          - Decrementa di 1 il children_count del genitore.
            Se va a 0, il genitore viene poppato dallo stack.
          - Se il nodo corrente ha children_count > 0, push nel stack.
        """
        stack = []

        for record in self.parsed_nodes:
            # Rimuovi dallo stack tutti i nodi in cima che hanno esaurito i figli
            while stack and stack[-1].children_count == 0:
                stack.pop()

            # Se lo stack non è vuoto, il top è il genitore
            if stack:
                parent_record = stack[-1]
                record.parent = parent_record
                parent_record.children_count -= 1

            # Se il nodo corrente ha children_count > 0, pusha
            if record.children_count > 0:
                stack.append(record)

        # Ora in record.parent abbiamo le relazioni parent-figlio.

        # Imposto in Blender la parentela
        for rec in self.parsed_nodes:
            if rec.parent is not None:
                parent_obj = rec.parent.blender_object
                child_obj = rec.blender_object
                child_obj.parent = parent_obj
                # Poiché abbiamo già assegnato matrix_world al child, e
                # vogliamo che rimanga "dov'è" in scena, impostiamo matrix_parent_inverse
                # uguale a parent_obj.matrix_world.inverted().
                child_obj.matrix_parent_inverse = parent_obj.matrix_world.inverted()

    def establish_root_node(self):
        """
        Facoltativo: se esiste un nodo chiamato '[root]', lo usiamo come root.
        Altrimenti, se ci sono più nodi top-level, potremmo creare un oggetto fittizio
        e metterli tutti come figli.
        """
        # 1) Trova eventuale nodo con name = '[root]'
        root_record = None
        for rec in self.parsed_nodes:
            if rec.name == "[root]":
                root_record = rec
                break

        if root_record:
            print(f"[INFO] Usa il nodo '{root_record.name}' come root.")
            return

        # 2) Calcola quanti nodi non hanno parent
        toplevel_nodes = [rec for rec in self.parsed_nodes if rec.parent is None]
        if len(toplevel_nodes) <= 1:
            # Un solo nodo top-level (o zero) => va già bene così
            return

        # 3) Crea un root fittizio
        print(f"[INFO] Creazione di un nodo [root] fittizio per {len(toplevel_nodes)} nodi top-level.")
        root_obj = bpy.data.objects.new("[root]", None)
        bpy.context.collection.objects.link(root_obj)
        root_obj.matrix_world = mathutils.Matrix.Identity(4)

        # Imposta la parentela
        for rec in toplevel_nodes:
            child_obj = rec.blender_object
            child_obj.parent = root_obj
            child_obj.matrix_parent_inverse = root_obj.matrix_world.inverted()

    def print_final_hierarchy(self):
        """Stampa a console la gerarchia risultante."""
        # Costruisce un mapping "nome -> record" per comodità
        name_to_record = {rec.name: rec for rec in self.parsed_nodes}

        # Trova tutti i top-level (parent=None)
        toplevel = [rec for rec in self.parsed_nodes if rec.parent is None]

        def _print_rec(rec, indent=0):
            print("  " * indent + f"+ {rec.name} ({rec.node_type})")
            # cerca i figli
            for child in self.parsed_nodes:
                if child.parent == rec:
                    _print_rec(child, indent+1)

        for rec in toplevel:
            _print_rec(rec)

    # ---------------------------------------------------
    # Funzioni di parsing di un singolo nodo/mesh/light
    # ---------------------------------------------------
    def parse_node_basic(self, chunk_data):
        """
        Legge i campi di un generico 'Node' (chunk ID=1) e restituisce:
        (node_name, matrixConvertita, children_count)
        """
        file_obj = io.BytesIO(chunk_data)

        # Legge nome
        node_name = OVOScene._read_string(file_obj)

        # Legge 16 float
        matrix_bytes = file_obj.read(64)
        matrix_values = struct.unpack("<16f", matrix_bytes)
        raw_matrix = mathutils.Matrix([matrix_values[i:i+4] for i in range(0,16,4)])

        # Legge children_count
        children_count = struct.unpack("<I", file_obj.read(4))[0]

        # Salta il target node
        _ = OVOScene._read_string(file_obj)

        # Converte la matrice in Blender
        matrix = OVOScene()._convert_matrix(raw_matrix)

        return node_name, matrix, children_count


# ====================================
#  OVOMesh (Mesh Node) Class
# ====================================
class OVOMesh:
    """
    Classe d'appoggio per il parsing di un chunk di tipo MESH (ID=18).
    Qui non memorizziamo nulla a lungo termine, ci limitiamo a restituire
    i dati parse_mesh_with_children().
    """

    @staticmethod
    def parse_mesh_with_children(chunk_data):
        """
        Legge i dati essenziali di una mesh e ritorna:
          (mesh_name, matrix, children_count, material_name, mesh_object)
        """
        file = io.BytesIO(chunk_data)
        mesh_name = OVOScene._read_string(file)

        matrix_bytes = file.read(64)
        matrix_values = struct.unpack('16f', matrix_bytes)
        raw_matrix = mathutils.Matrix([matrix_values[i:i+4] for i in range(0,16,4)])
        matrix = OVOScene()._convert_matrix(raw_matrix)

        children_count = struct.unpack('I', file.read(4))[0]
        _ = OVOScene._read_string(file)  # target node (ignorato qui)
        mesh_subtype = struct.unpack('B', file.read(1))[0]

        material_name = OVOScene._read_string(file)

        # salta bounding sphere, bounding box, ecc. finché non arriviamo ai vertici
        file.seek(4 + 12 + 12, 1)  # radius + minBox + maxBox
        physics_flag = struct.unpack('B', file.read(1))[0]
        if physics_flag:
            # salta i dati di fisica
            # NB: la dimensione esatta dipende dalla struttura, qui semplificato
            # in un contesto reale dovremmo leggere con precisione
            pass_len = OVOMesh._skip_physics_data(file)

        lod_count = struct.unpack('I', file.read(4))[0]
        if lod_count == 0:
            # caso limite
            mesh_data = bpy.data.meshes.new(mesh_name)
            obj = bpy.data.objects.new(mesh_name, mesh_data)
            return mesh_name, matrix, children_count, material_name, obj

        # Per semplicità leggiamo solo LOD0
        vertex_count, face_count = struct.unpack('2I', file.read(8))

        vertices = []
        faces = []

        for _ in range(vertex_count):
            # posizione (3 float)
            pos = struct.unpack('3f', file.read(12))
            # normal data (1 uint)
            _normalData = struct.unpack('I', file.read(4))[0]
            # uv data (1 uint)
            _uvData = struct.unpack('I', file.read(4))[0]
            # tangent (1 uint)
            _ = file.read(4)
            vertices.append(pos)

        for _ in range(face_count):
            face = struct.unpack('3I', file.read(12))
            faces.append(face)

        # Crea la mesh
        mesh_data = bpy.data.meshes.new(mesh_name)
        mesh_data.from_pydata(vertices, [], faces)
        mesh_data.update()

        mesh_object = bpy.data.objects.new(mesh_name, mesh_data)

        return mesh_name, matrix, children_count, material_name, mesh_object

    @staticmethod
    def _skip_physics_data(file_obj):
        """
        Funzione d'appoggio per saltare i dati di fisica.
        NON è un parse rigoroso: esegue un 'seek' veloce.
        """
        # Legge un blocco standard di 48 byte (PhysProps), poi
        # vede se c'è 1 o più hull e li salta.
        # Per semplicità qui facciamo finta che chunk_data non contenga hull complessi.
        # In un parser completo bisognerebbe leggere i 'nrOfHulls' e saltare i dati relativi.
        start_pos = file_obj.tell()

        # Legge i 48 byte
        file_obj.seek(48, 1)

        # Recupera il numero di hull
        # NB: offset nel nostro ipotetico struct
        file_obj.seek(-8, 1)  # torniamo indietro per leggere 'nrOfHulls'
        nr_hulls = struct.unpack('I', file_obj.read(4))[0]
        file_obj.seek(4, 1)  # skip un eventuale pad

        # Ora saltiamo i hull se >0
        for _ in range(nr_hulls):
            # es. 8 byte per numVert e numFace,
            # 12 per centroid, poi vertici e facce
            nr_vertices = struct.unpack('I', file_obj.read(4))[0]
            nr_faces = struct.unpack('I', file_obj.read(4))[0]
            file_obj.seek(12, 1)  # centroid
            # salta i vertici
            file_obj.seek(nr_vertices * 12, 1)  # 3 float = 12 byte
            # salta le facce
            file_obj.seek(nr_faces * 12, 1)  # 3 int = 12 byte

        end_pos = file_obj.tell()
        return end_pos - start_pos


# ====================================
#  OVOMaterial (Material) Class
# ====================================
class OVOMaterial:
    """Rappresenta un materiale OVO."""

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

        mat = OVOMaterial(name, base_color, roughness, metallic, transparency, emissive, textures)
        return mat

    def create_blender_material(self, texture_directory):
        mat = bpy.data.materials.new(name=self.name)
        mat.use_nodes = True
        bsdf = None
        for node in mat.node_tree.nodes:
            if node.type == 'BSDF_PRINCIPLED':
                bsdf = node
                break
        if bsdf is None:
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
        self.blender_material = mat
        return mat


# ====================================
#  OVOLight (Light Node) Class
# ====================================
class OVOLight:
    """
    Classe d'appoggio per il parsing di un chunk di tipo LIGHT (ID=16).
    """

    @staticmethod
    def parse_light(chunk_data):
        file = io.BytesIO(chunk_data)
        light_name = OVOScene._read_string(file)

        matrix_bytes = file.read(64)
        matrix_values = struct.unpack("<16f", matrix_bytes)
        raw_matrix = mathutils.Matrix([matrix_values[i:i+4] for i in range(0,16,4)])
        matrix = OVOScene()._convert_matrix(raw_matrix)

        children_count = struct.unpack("<I", file.read(4))[0]
        _target = OVOScene._read_string(file)  # ignora

        light_type = struct.unpack("<B", file.read(1))[0]
        color = struct.unpack("<3f", file.read(12))
        radius = struct.unpack("<f", file.read(4))[0]
        direction = struct.unpack("<3f", file.read(12))
        cutoff = struct.unpack("<f", file.read(4))[0]
        spot_exponent = struct.unpack("<f", file.read(4))[0]
        shadow = struct.unpack("<B", file.read(1))[0]
        volumetric = struct.unpack("<B", file.read(1))[0]

        # Crea effettivamente la LightData di Blender
        light_data = None
        if light_type == 0:  # OMNI
            light_data = bpy.data.lights.new(name=light_name, type='POINT')
            light_data.color = color
            light_data.energy = radius * 10
            light_data.use_shadow = bool(shadow)
        elif light_type == 1:  # DIRECTIONAL
            light_data = bpy.data.lights.new(name=light_name, type='SUN')
            light_data.color = color
            light_data.energy = radius * 10
            light_data.use_shadow = bool(shadow)
        elif light_type == 2:  # SPOT
            light_data = bpy.data.lights.new(name=light_name, type='SPOT')
            light_data.color = color
            light_data.energy = radius * 10
            light_data.spot_size = cutoff
            light_data.spot_blend = spot_exponent / 10.0
            light_data.use_shadow = bool(shadow)

        return light_name, matrix, children_count, light_data


# ====================================
#  OVOScene (solo per funzioni statiche)
# ====================================
class OVOScene:
    """Funzioni di supporto (lettura string e conversione matrix)."""

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
        """
        Dato che nel formato OVO la matrice è pensata per OpenGL (row-major),
        la trasponiamo e applichiamo la rotazione di 90° su X per passare a Blender.
        """
        matrix.transpose()
        conversion_matrix = mathutils.Matrix([
            [1, 0, 0, 0],
            [0, 0, -1, 0],
            [0, 1, 0, 0],
            [0, 0, 0, 1]
        ])
        return conversion_matrix @ matrix


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
        print(f"⚠ Warning: Failed to unregister properly - {e}")


if __name__ == "__main__":
   register()
