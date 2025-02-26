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

# ===================================
#   Node Information Storage
# ===================================
class NodeRecord:
    """
    Memorizza info su un nodo/mesh/light OVO:
      - name
      - node_type (NODE, MESH, LIGHT)
      - children_count
      - blender_object (creato in parse)
      - parent (NodeRecord)
      - raw_matrix: la matrice letta dal file, row-major
    """
    def __init__(self, name, node_type, children_count, blender_object, raw_matrix):
        self.name = name
        self.node_type = node_type
        self.children_count = children_count
        self.blender_object = blender_object
        self.parent = None
        # Salviamo la matrice "raw" di 4x4 float letta da chunk, senza rotazione
        self.raw_matrix = raw_matrix

    def __repr__(self):
        return (f"NodeRecord(name={self.name}, type={self.node_type}, "
                f"children_count={self.children_count})")


# ====================================
#   OVO Chunk
# ====================================
class OVOChunk:
    def __init__(self, chunk_id, chunk_size, data):
        self.chunk_id = chunk_id
        self.chunk_size = chunk_size
        self.data = data

    @staticmethod
    def read_chunk(file):
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
    def __init__(self, filepath):
        self.filepath = filepath
        self.chunks = []
        self.materials = {}
        self.texture_directory = os.path.dirname(filepath)
        self.parsed_nodes = []  # List[NodeRecord]

    def read_ovo_file(self):
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
        print(f"[OVOImporter.import_scene] Inizio import del file: {self.filepath}")
        if not self.read_ovo_file():
            return {'CANCELLED'}

        self.parse_chunks()
        self.build_hierarchy_stack_approach()
        self.establish_root_node()

        # Fase finale: assegna matrix_world a seconda se parent == [root]
        self.apply_matrices_with_partial_rotation()

        print("[OVOImporter.import_scene] Gerarchia finale importata:")
        self.print_final_hierarchy()
        print("[OVOImporter.import_scene] Import completato con successo.")
        return {'FINISHED'}

    def parse_chunks(self):
        """
        Leggiamo i chunk e creiamo i NodeRecord, salvando la raw_matrix
        ma SENZA applicare la rotazione. L'oggetto in Blender viene creato,
        ma la matrix_world per ora resta identity (o la settiamo dopo la fase finale).
        """
        print("[OVOImporter.parse_chunks] Inizio analisi chunk.")
        for i, chunk in enumerate(self.chunks):
            cid = chunk.chunk_id
            print(f"  > Chunk #{i} : ID={cid}, size={chunk.chunk_size}")

            if cid == 9:
                print("    [INFO] Trovato chunk 'Material'")
                material = OVOMaterial.parse_material(chunk.data)
                mat = material.create_blender_material(self.texture_directory)
                self.materials[material.name] = material
                print(f"    [INFO] Material creato: {material.name}")
                continue

            if cid == 1:
                node_name, raw_matrix, children_count = self.parse_node_basic_raw(chunk.data)
                node_obj = bpy.data.objects.new(node_name, None)
                bpy.context.collection.objects.link(node_obj)
                # Non assegniamo la matrix_world definitiva qui
                node_obj.matrix_world = mathutils.Matrix.Identity(4)

                record = NodeRecord(node_name, "NODE", children_count, node_obj, raw_matrix)
                self.parsed_nodes.append(record)
                print(f"    [INFO] Creato NodeRecord: {record}")
                continue

            if cid == 16:
                light_name, raw_matrix, children_count, light_data = self.parse_light_raw(chunk.data)
                light_obj = bpy.data.objects.new(light_name, light_data)
                bpy.context.collection.objects.link(light_obj)
                light_obj.matrix_world = mathutils.Matrix.Identity(4)

                record = NodeRecord(light_name, "LIGHT", children_count, light_obj, raw_matrix)
                self.parsed_nodes.append(record)
                print(f"    [INFO] Creato NodeRecord: {record}")
                continue

            if cid == 18:
                mesh_name, raw_matrix, children_count, material_name, mesh_obj = \
                    self.parse_mesh_raw(chunk.data)

                if material_name in self.materials:
                    mat = self.materials[material_name].blender_material
                    if mat:
                        if not mesh_obj.data.materials:
                            mesh_obj.data.materials.append(mat)
                        else:
                            mesh_obj.data.materials[0] = mat

                bpy.context.collection.objects.link(mesh_obj)
                mesh_obj.matrix_world = mathutils.Matrix.Identity(4)

                record = NodeRecord(mesh_name, "MESH", children_count, mesh_obj, raw_matrix)
                self.parsed_nodes.append(record)
                print(f"    [INFO] Creato NodeRecord: {record}")
                continue

            print(f"    [WARNING] Chunk ID={cid} non gestito (ignorato).")

        print("[OVOImporter.parse_chunks] Fine analisi chunk.")

    def build_hierarchy_stack_approach(self):
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
                child_obj = rec.blender_object
                parent_obj = rec.parent.blender_object
                child_obj.parent = parent_obj
                child_obj.matrix_parent_inverse = parent_obj.matrix_world.inverted()
                print(f"     [BLENDER] '{rec.name}' -> parent = '{rec.parent.name}'")

    def establish_root_node(self):
        print("[OVOImporter.establish_root_node] Controllo esistenza '[root]' e nodi top-level.")
        root_record = None
        for rec in self.parsed_nodes:
            if rec.name == "[root]":
                root_record = rec
                print(f"  [INFO] Uso il nodo '{rec.name}' come root esplicito.")
                return  # fine

        # se non c'è root, e ci sono 2+ top-level, creiamo un root fittizio
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
        Applica:
          - trasposizione + 90° su X per i nodi figli diretti di '[root]'
          - solo trasposizione per i nodi figli di altri nodi.
        NB: Se un nodo E' root, non facciamo nulla (lasciamo identità).
        """
        print("[OVOImporter] apply_matrices_with_partial_rotation: inizio.")
        for rec in self.parsed_nodes:
            # se rec è il root, la matrix_world rimane identity
            if rec.name == "[root]":
                print(f"   - skip rotation for [root]")
                continue

            # costruiamo la matrice dal raw
            local_mat = self._transpose_only(rec.raw_matrix)

            # controlla se parent == [root]
            if rec.parent and rec.parent.name == "[root]":
                # applichiamo la rotazione
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

            # se rec ha un parent, blender calcolerà matrix_world = parent.matrix_world * local_mat
            # conviene settare child_obj.matrix_local = local_mat
            # NB: per farlo in Blender, possiamo reimpostare matrix_parent_inverse (oppure .matrix_local)
            # ma .matrix_local non si può scrivere direttamente se parent is not None, quindi si fa:
            rec.blender_object.matrix_basis = local_mat

    def _transpose_only(self, matrix):
        """
        Data la matrice row-major proveniente dal file, la trasponiamo ma NON ruotiamo.
        """
        tmp = matrix.copy()
        tmp.transpose()
        return tmp

    def print_final_hierarchy(self):
        print("[OVOImporter.print_final_hierarchy] Inizio stampa.\n")
        top_nodes = [r for r in self.parsed_nodes if r.parent is None]

        def _print_rec(rec, indent=0):
            print("  " * indent + f"+ {rec.name} ({rec.node_type})")
            for child in self.parsed_nodes:
                if child.parent == rec:
                    _print_rec(child, indent+1)

        for top in top_nodes:
            _print_rec(top)
        print("\n[OVOImporter.print_final_hierarchy] Fine stampa.")

    # ----------------------------------------------------------------------
    #   Funzioni di parse "raw" (senza rotazione) per node, mesh, light
    # ----------------------------------------------------------------------
    def parse_node_basic_raw(self, chunk_data):
        file_obj = io.BytesIO(chunk_data)
        node_name = OVOScene._read_string(file_obj)

        # Leggiamo i 16 float in row-major
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
        raw_matrix = mathutils.Matrix([matrix_values[i:i+4] for i in range(0,16,4)])

        children_count = struct.unpack('I', file.read(4))[0]
        _target = OVOScene._read_string(file)
        mesh_subtype = struct.unpack('B', file.read(1))[0]
        material_name = OVOScene._read_string(file)

        print(f"[parse_mesh_raw] Mesh='{mesh_name}', child={children_count}, mat='{material_name}'")

        # bounding sphere + minBox + maxBox
        file.seek(4 + 12 + 12, 1)
        physics_flag = struct.unpack('B', file.read(1))[0]
        if physics_flag:
            OVOMesh._skip_physics_data(file)

        lod_count = struct.unpack('I', file.read(4))[0]
        if lod_count == 0:
            mesh_data = bpy.data.meshes.new(mesh_name)
            obj = bpy.data.objects.new(mesh_name, mesh_data)
            return mesh_name, raw_matrix, children_count, material_name, obj

        vertex_count, face_count = struct.unpack('2I', file.read(8))
        vertices = []
        faces = []
        for _ in range(vertex_count):
            pos = struct.unpack('3f', file.read(12))
            _normalData = struct.unpack('I', file.read(4))[0]
            _uvData = struct.unpack('I', file.read(4))[0]
            _tangent = file.read(4)
            vertices.append(pos)

        for _ in range(face_count):
            face = struct.unpack('3I', file.read(12))
            faces.append(face)

        mesh_data = bpy.data.meshes.new(mesh_name)
        mesh_data.from_pydata(vertices, [], faces)
        mesh_data.update()
        mesh_obj = bpy.data.objects.new(mesh_name, mesh_data)
        print(f"[parse_mesh_raw] creato obj '{mesh_name}' con {len(vertices)} vert e {len(faces)} facce.")
        return mesh_name, raw_matrix, children_count, material_name, mesh_obj

    def parse_light_raw(self, chunk_data):
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
#  OVOMaterial
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
        ttypes = ["albedo","normal","height","roughness","metalness"]
        for t in ttypes:
            tname = OVOScene._read_string(file)
            textures[t] = tname if tname != "[none]" else None

        return OVOMaterial(name, base_color, roughness, metallic, transparency, emissive, textures)

    def create_blender_material(self, texdir):
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
        bsdf.inputs["Base Color"].default_value = (*self.base_color, 1.0)
        bsdf.inputs["Roughness"].default_value = self.roughness
        bsdf.inputs["Metallic"].default_value = self.metallic
        if self.transparency < 1.0:
            mat.blend_method = 'BLEND'
            mat.shadow_method = 'HASHED'
            bsdf.inputs["Alpha"].default_value = self.transparency
        if "Emission" in bsdf.inputs:
            bsdf.inputs["Emission"].default_value = (*self.emissive,1.0)
        self.blender_material = mat
        return mat

# ====================================
#  OVOLight
# ====================================
class OVOLight:
    @staticmethod
    def _create_blender_light_data(name, ltype, color, radius, cutoff, sp_exponent, shadow):
        if ltype == 0:  # point
            ldata = bpy.data.lights.new(name=name, type='POINT')
            ldata.color = color
            ldata.energy = radius*10
            ldata.use_shadow = bool(shadow)
            return ldata
        elif ltype == 1: # sun
            ldata = bpy.data.lights.new(name=name, type='SUN')
            ldata.color = color
            ldata.energy = radius*10
            ldata.use_shadow = bool(shadow)
            return ldata
        elif ltype == 2: # spot
            ldata = bpy.data.lights.new(name=name, type='SPOT')
            ldata.color = color
            ldata.energy = radius*10
            ldata.spot_size = cutoff
            ldata.spot_blend = sp_exponent / 10.0
            ldata.use_shadow = bool(shadow)
            return ldata
        else:
            ldata = bpy.data.lights.new(name=name, type='POINT')
            return ldata

# ====================================
#  OVOScene (statiche)
# ====================================
class OVOScene:
    @staticmethod
    def _read_string(file):
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
    bl_idname = "import_scene.ovo"
    bl_label = "Import OVO"
    filename_ext = ".ovo"
    filter_glob: StringProperty(default="*.ovo", options={'HIDDEN'})

    def execute(self, context):
        importer = OVOImporter(self.filepath)
        res = importer.import_scene()
        bpy.context.view_layer.update()
        return res

def menu_func_import(self, context):
    self.layout.operator(OT_ImportOVO.bl_idname, text="OverVision Object (.ovo)")

def register():
    bpy.utils.register_class(OT_ImportOVO)
    bpy.types.TOPBAR_MT_file_import.append(menu_func_import)

def unregister():
    bpy.types.TOPBAR_MT_file_import.remove(menu_func_import)
    bpy.utils.unregister_class(OT_ImportOVO)


if __name__ == "__main__":
    register()


"""""
if __name__ == "__main__":
    print("[MAIN] Avvio test OVOImporter su IDE...")

    test_path = "C:\\Users\\kevin\\Downloads\\output.ovo"
    importer = OVOImporter(test_path)
    import_result = importer.import_scene()
    print(f"[MAIN] Risultato import: {import_result}")
    print("[MAIN] Fine esecuzione script.")
"""