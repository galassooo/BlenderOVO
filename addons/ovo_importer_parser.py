# ================================================================
#  OVO IMPORTER PARSER
# ================================================================
# This module is the main parsing stage of your importer. It:
#   1) Reads the entire .ovo file chunk-by-chunk using the OVOChunk class.
#   2) Interprets each chunk (MATERIAL, NODE, LIGHT, MESH) by converting
#      the raw binary data into Python objects (NodeRecord and OVOMaterial).
#   3) Stores the parsed materials in a dictionary and nodes in a list.
#
# All low-level utilities (e.g. half-float decoding and null-terminated string reading)
# are imported from the utility module.
# ================================================================

# --------------------------------------------------------
# IMPORTS
# --------------------------------------------------------
import math
import os
import io
import struct
import mathutils

try:
    from .ovo_importer_utils import half_to_float, decode_half2x16, read_null_terminated_string
    from .ovo_importer_chunk import OVOChunk
    from .ovo_importer_node import OVOMaterial, NodeRecord, OVOPhysicsData
    from .ovo_types import ChunkType, LightType
    from .ovo_log import log
except ImportError:
    from ovo_importer_utils import half_to_float, decode_half2x16, read_null_terminated_string
    from ovo_importer_chunk import OVOChunk
    from ovo_importer_node import OVOMaterial, NodeRecord, OVOPhysicsData
    from ovo_types import ChunkType
    from ovo_log import log


# --------------------------------------------------------
# OVOImporterParser
# --------------------------------------------------------

class OVOImporterParser:
    """
    The main parser class for reading an .ovo file.

    This class:
      - Opens the file and reads its contents in chunks.
      - Interprets each chunk based on its chunk ID:
          - MATERIAL chunks are converted into OVOMaterial objects.
          - NODE, LIGHT, and MESH chunks become NodeRecord objects.
      - All parsed data is stored in:
          - self.materials: a dictionary of {materialName: OVOMaterial}
          - self.node_records: a list of NodeRecord objects
    """

    def __init__(self, filepath: str):
        """
        Initialize the parser with the file path.

        :param filepath: Full path to the .ovo file to import.
        """
        self.filepath = filepath
        self.chunks = []
        self.materials = {}
        self.node_records = []

    # --------------------------------------------------------
    # Parse File
    # --------------------------------------------------------
    def parse_file(self) -> bool:
        """
        Reads the .ovo file in its entirety, gathering chunks and interpreting them.

        Steps:
          1. Check if the file exists. If not, log an error and return False.
          2. Open the file in binary mode and repeatedly call OVOChunk.read_chunk().
          3. For each chunk read, call _parse_chunk() to interpret its contents.

        :return: True if the file was successfully read and parsed; otherwise, False.
        """
        if not os.path.isfile(self.filepath):
            log(f"[OVOImporterParser] ERROR: File not found: {self.filepath}", category="ERROR")
            return False

        # Open file and read all chunks.
        with open(self.filepath, "rb") as f:
            while True:
                chunk = OVOChunk.read_chunk(f)
                if chunk is None:
                    break
                self.chunks.append(chunk)

        # Parse each chunk into proper data structures.
        for chunk in self.chunks:
            self._parse_chunk(chunk)

        return True

    # --------------------------------------------------------
    # Parse Chunk
    # --------------------------------------------------------
    def _parse_chunk(self, chunk: OVOChunk):
        """
        Dispatches the chunk to the appropriate parse method based on its ID.

        Recognized chunk IDs:
          - ChunkType.MATERIAL: Processed via _parse_material().
          - ChunkType.NODE: Processed via _parse_node().
          - ChunkType.LIGHT: Processed via _parse_light().
          - ChunkType.MESH: Processed via _parse_mesh().

        Any unhandled chunk IDs are logged as warnings.

        :param chunk: The OVOChunk to parse.
        """
        if chunk.chunk_id == ChunkType.MATERIAL:
            mat = self._parse_material(chunk.data)
            self.materials[mat.name] = mat
        elif chunk.chunk_id == ChunkType.NODE:
            node_rec = self._parse_node(chunk.data)
            self.node_records.append(node_rec)
        elif chunk.chunk_id == ChunkType.LIGHT:
            light_rec = self._parse_light(chunk.data)
            self.node_records.append(light_rec)
        elif chunk.chunk_id == ChunkType.MESH:
            mesh_rec = self._parse_mesh(chunk.data)
            self.node_records.append(mesh_rec)
        else:
            log(f"[OVOImporterParser] WARNING: Unhandled chunk ID={chunk.chunk_id}", category="WARNING")

    # ========================================================
    # Parsing Methods for Specific Chunk Types
    # ========================================================

    # --------------------------------------------------------
    # Parse Material
    # --------------------------------------------------------
    def _parse_material(self, data: bytes) -> OVOMaterial:
        """
        Parses a MATERIAL chunk (ChunkType.MATERIAL, typically ID=9).

        Expected data:
          - Material name (null-terminated string)
          - Emissive color (3 floats)
          - Base color (3 floats)
          - Roughness (float)
          - Metallic (float)
          - Transparency (float)
          - Five texture strings (albedo, normal, height, roughness, metalness)

        :param data: Raw bytes from the chunk.
        :return: An OVOMaterial instance populated with the parsed values.
        """
        f = io.BytesIO(data)
        name = read_null_terminated_string(f)
        emissive = struct.unpack("<3f", f.read(12))
        base_color = struct.unpack("<3f", f.read(12))
        roughness = struct.unpack("<f", f.read(4))[0]
        metallic = struct.unpack("<f", f.read(4))[0]
        transparency = struct.unpack("<f", f.read(4))[0]

        # Read the five texture strings.
        ttypes = ["albedo", "normal", "height", "roughness", "metalness"]
        textures = {}
        for t in ttypes:
            tname = read_null_terminated_string(f)
            if tname == "[none]":
                tname = None
            textures[t] = tname

        log(f"Parsed material: '{name}' | BaseColor={base_color}, Roughness={roughness:.2f}, Metallic={metallic:.2f}",category="MATERIAL", indent=1)
        return OVOMaterial(name, base_color, roughness, metallic, transparency, emissive, textures)

    # --------------------------------------------------------
    # Parse Node
    # --------------------------------------------------------
    def _parse_node(self, data: bytes) -> NodeRecord:
        """
        Parses a generic NODE chunk (ChunkType.NODE, ID=1).

        Expected data:
          - Node name (null-terminated string)
          - 4x4 transformation matrix (16 floats, in row-major order)
          - children_count (unsigned int)
          - A target string (ignored)

        :param data: Raw bytes of the node chunk.
        :return: A NodeRecord with node_type set to "NODE".
        """
        f = io.BytesIO(data)
        node_name = read_null_terminated_string(f)
        mat_vals = struct.unpack("<16f", f.read(64))
        raw_matrix = [mat_vals[i:i + 4] for i in range(0, 16, 4)]
        children_count = struct.unpack("<I", f.read(4))[0]
        _ = read_null_terminated_string(f)

        log(f"Parsed node: '{node_name}' | Children={children_count}", category="NODE", indent=1)
        return NodeRecord(node_name, "NODE", children_count, raw_matrix)

    # --------------------------------------------------------
    # Parse Light
    # --------------------------------------------------------
    def _parse_light(self, data: bytes) -> NodeRecord:
        """
        Parses a LIGHT chunk (ChunkType.LIGHT, ID=16).

        Expected data:
          - Light name (null-terminated string)
          - 4x4 transformation matrix (16 floats, row-major)
          - children_count (unsigned int)
          - A target string (ignored)
          - Light type (1 byte)
          - Color (3 floats)
          - Radius (float)
          - Direction (3 floats)
          - Cutoff angle (float)
          - Spot exponent (float)
          - Shadow flag (1 byte)
          - Volumetric flag (1 byte)
        :param data: Raw bytes of the light chunk.
        :return: A NodeRecord with node_type set to "LIGHT", filled with light parameters.
        """
        f = io.BytesIO(data)
        light_name = read_null_terminated_string(f)
        mat_vals = struct.unpack("<16f", f.read(64))
        raw_matrix = [mat_vals[i:i + 4] for i in range(0, 16, 4)]
        children_count = struct.unpack("<I", f.read(4))[0]
        _ = read_null_terminated_string(f)

        light_type = struct.unpack("<B", f.read(1))[0]
        color = struct.unpack("<3f", f.read(12))
        radius = struct.unpack("<f", f.read(4))[0]
        direction = struct.unpack("<3f", f.read(12))
        cutoff = struct.unpack("<f", f.read(4))[0]
        spot_exp = struct.unpack("<f", f.read(4))[0]
        shadow = struct.unpack("<B", f.read(1))[0]
        volumetric = struct.unpack("<B", f.read(1))[0]

        rec = NodeRecord(light_name, "LIGHT", children_count, raw_matrix)
        rec.light_type = light_type
        rec.color = color
        rec.radius = radius
        rec.direction = direction
        rec.cutoff = cutoff
        rec.spot_exponent = spot_exp
        rec.shadow = shadow
        rec.volumetric = volumetric

        # Handle direction correction for directional and spot lights
        if light_type == LightType.DIRECTIONAL or light_type == LightType.SPOT:
            # Blender's default light direction (-Z axis)
            default_dir = mathutils.Vector((0, 0, -1))

            # Apply +90° rotation around X to reverse the -90° export correction
            conversion = mathutils.Matrix.Rotation(math.radians(90), 3, 'X')
            corrected_dir = conversion @ mathutils.Vector(direction)

            # Normalize and compute the quaternion
            target_dir = corrected_dir.normalized()
            log(f"Light '{light_name}' direction: raw={direction}, corrected={tuple(target_dir)}", category="LIGHT", indent=1)

            rec.light_quat = default_dir.rotation_difference(target_dir)
        else:
            default_dir = mathutils.Vector((0, 0, -1))
            target_dir = mathutils.Vector(direction).normalized()
            rec.light_quat = default_dir.rotation_difference(target_dir)

        log(f"Parsed light: '{light_name}' | Type={light_type}, Color={color}, Radius={radius:.2f}", category="LIGHT",indent=1)
        return rec

    # --------------------------------------------------------
    # Parse Mesh
    # --------------------------------------------------------
    def _parse_mesh(self, data: bytes) -> NodeRecord:
        """
        Parses a MESH chunk (ChunkType.MESH, ID=18).

        Expected data:
          - Mesh name (null-terminated string)
          - 4x4 transformation matrix (16 floats, row-major)
          - children_count (unsigned int)
          - A target string (ignored)
          - Mesh subtype (1 byte)
          - Material name (null-terminated string)
          - Bounding sphere (float) followed by bounding box (3 floats each for min and max)
          - Physics flag (1 byte) and, if present, physics data (see _read_physics_data)
          - LOD count (unsigned int)
          - If LOD count > 0: vertex_count (unsigned int), face_count (unsigned int),
            followed by the vertex data (position, packed normal, packed UV, tangent) and face indices.

        :param data: Raw bytes of the mesh chunk.
        :return: A NodeRecord with node_type set to "MESH", including geometry and physics if available.
        """
        f = io.BytesIO(data)
        mesh_name = read_null_terminated_string(f)
        mvals = struct.unpack("<16f", f.read(64))
        raw_matrix = [mvals[i:i + 4] for i in range(0, 16, 4)]
        children_count = struct.unpack("<I", f.read(4))[0]
        _ = read_null_terminated_string(f)
        mesh_subtype = struct.unpack("<B", f.read(1))[0]
        material_name = read_null_terminated_string(f)

        # Read bounding data
        _ = struct.unpack("<f", f.read(4))[0]
        _ = f.read(12)  # min box
        _ = f.read(12)  # max box

        physics_flag = struct.unpack("<B", f.read(1))[0]
        physics_data = None
        if physics_flag:
            physics_data = self._read_physics_data(f)

        lod_count = struct.unpack("<I", f.read(4))[0]

        rec = NodeRecord(mesh_name, "MESH", children_count, raw_matrix)
        rec.material_name = material_name
        rec.physics_data = physics_data
        rec.lod_count = lod_count

        if lod_count == 0:
            log(f"Mesh '{mesh_name}' has no LODs — skipping geometry", category="MESH", indent=1)
            return rec

        # Read geometry: number of vertices and faces.
        vertex_count, face_count = struct.unpack("<2I", f.read(8))
        vertices = []
        faces = []
        uvs = []

        for _ in range(vertex_count):
            px, py, pz = struct.unpack("<3f", f.read(12))
            # Skip the packed normal.
            _ = struct.unpack("<I", f.read(4))[0]
            uv_data = struct.unpack("<I", f.read(4))[0]
            f.read(4)  # Skip tangent data.
            vertices.append((px, py, pz))
            uv = decode_half2x16(uv_data)
            uvs.append(uv)

        for _ in range(face_count):
            idxs = struct.unpack("<3I", f.read(12))
            faces.append(idxs)

        rec.vertices = vertices
        rec.faces = faces
        rec.uvs = uvs

        log(f"Parsed mesh: '{mesh_name}' | Vertices: {vertex_count}, Faces: {face_count}", category="MESH", indent=1)
        return rec

    # --------------------------------------------------------
    # Read Physics Data for Mesh Chunks
    # --------------------------------------------------------
    def _read_physics_data(self, f) -> OVOPhysicsData:
        """
        Reads the physics section from a mesh chunk.

        Expected data:
          - object type (1 byte)
          - contCollision (1 byte)
          - collide_with_rb (1 byte)
          - hull type (1 byte)
          - mass center (3 floats) [ignored]
          - Mass, static friction, dynamic friction, bounciness, linear damping, angular damping (6 floats)
          - Number of hulls (unsigned int)
          - Padding (unsigned int)
          - Two reserved pointers (8+8 bytes)
          - For each hull: number of vertices, number of faces, hull centroid,
            then the vertices (each 3 floats) and faces (each 3 unsigned ints) – which are skipped.

        :param f: A file-like object (BytesIO) positioned at the start of physics data.
        :return: An OVOPhysicsData instance with the parsed physics parameters.
        """
        obj_type = struct.unpack("<B", f.read(1))[0]
        _ = f.read(1)  # contCollision
        _ = f.read(1)  # collide_with_rb
        hull_type = struct.unpack("<B", f.read(1))[0]
        _ = f.read(12)  # mass center

        mass, static_fric, dyn_fric, bounciness, lin_damp, ang_damp = struct.unpack("<6f", f.read(24))
        nr_hulls = struct.unpack("<I", f.read(4))[0]
        _ = f.read(4)  # padding
        _ = f.read(16)  # two reserved pointers

        # Skip geometry for each hull.
        for _ in range(nr_hulls):
            n_verts = struct.unpack("<I", f.read(4))[0]
            n_faces = struct.unpack("<I", f.read(4))[0]
            f.read(12)  # hull centroid
            for _ in range(n_verts):
                f.read(12)
            for _ in range(n_faces):
                f.read(12)

        return OVOPhysicsData(obj_type, hull_type, mass, static_fric, dyn_fric, bounciness, lin_damp, ang_damp)

