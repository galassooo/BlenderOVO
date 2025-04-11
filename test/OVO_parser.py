import struct
import numpy as np
import glm  # PyGLM per la compatibilità con GLM
from enum import IntEnum
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Any, BinaryIO


class ChunkType(IntEnum):
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


class MeshSubtype(IntEnum):
    DEFAULT = 0
    NORMALMAPPED = 1
    TESSELLATED = 2
    LAST = 3


class LightSubtype(IntEnum):
    OMNI = 0
    DIRECTIONAL = 1
    SPOT = 2
    LAST = 3


class OVOParser:
    def __init__(self, verbose=True):
        self.verbose = verbose
        self.materials = {}
        self.nodes = {}
        self.base_path = "./"

        # Dati per validazione
        self.validation_data = {
            "version": None,
            "materials": [],
            "nodes": [],
            "meshes": [],
            "lights": []
        }

    def log(self, message):
        if self.verbose:
            print(message)

    def read_string(self, file: BinaryIO) -> str:
        result = bytearray()
        while True:
            char = file.read(1)
            if not char or char == b'\0':
                break
            result.extend(char)
        return result.decode('utf-8')

    def read_chunk_header(self, file: BinaryIO) -> Tuple[int, int]:
        data = file.read(8)
        if len(data) < 8:
            return None, None
        chunk_id, chunk_size = struct.unpack("<II", data)
        return chunk_id, chunk_size

    def decompress_normal(self, packed_normal: int) -> Tuple[float, float, float]:
        # Implementazione della decompressione di normali usando PyGLM
        normal = glm.unpackSnorm3x10_1x2(packed_normal)
        return normal.x, normal.y, normal.z

    def decompress_tex_coords(self, packed_tex_coords: int) -> Tuple[float, float]:
        # Implementazione della decompressione di coordinate UV usando PyGLM
        tex_coords = glm.unpackHalf2x16(packed_tex_coords)
        return tex_coords.x, tex_coords.y

    def parse_ovo_file(self, filepath: str) -> Dict:
        """
        Parse un file OVO e restituisce i dati di validazione
        """
        with open(filepath, 'rb') as file:
            while True:
                chunk_id, chunk_size = self.read_chunk_header(file)
                if chunk_id is None:
                    break

                self.log(
                    f"Parsing chunk {chunk_id} ({ChunkType(chunk_id).name if chunk_id in ChunkType.__members__.values() else 'UNKNOWN'}), size: {chunk_size}")

                # Leggi i dati del chunk
                chunk_data = file.read(chunk_size)

                # Elabora i dati in base al tipo di chunk
                if chunk_id == ChunkType.OBJECT:
                    self._parse_object_chunk(chunk_data)
                elif chunk_id == ChunkType.NODE:
                    self._parse_node_chunk(chunk_data)
                elif chunk_id == ChunkType.MATERIAL:
                    self._parse_material_chunk(chunk_data)
                elif chunk_id == ChunkType.MESH:
                    self._parse_mesh_chunk(chunk_data)
                elif chunk_id == ChunkType.LIGHT:
                    self._parse_light_chunk(chunk_data)
                # Aggiungi altri tipi di chunk secondo necessità

        return self.validation_data

    def _parse_object_chunk(self, data: bytes):
        # Estrai la versione
        version = struct.unpack("<I", data[:4])[0]
        self.validation_data["version"] = version
        self.log(f"OVO Version: {version}")

    def _parse_node_chunk(self, data: bytes):
        # Implementa il parsing del nodo
        position = 0

        # Leggi il nome del nodo
        node_name = ""
        while data[position] != 0:
            node_name += chr(data[position])
            position += 1
        position += 1  # Salta il terminatore null

        # Leggi la matrice
        matrix = struct.unpack("<16f", data[position:position + 64])
        position += 64

        # Numero di figli
        children_count = struct.unpack("<I", data[position:position + 4])[0]
        position += 4

        # Target node
        target_name = ""
        while position < len(data) and data[position] != 0:
            target_name += chr(data[position])
            position += 1

        # Aggiungi ai dati di validazione
        node_data = {
            "name": node_name,
            "matrix": matrix,
            "children_count": children_count,
            "target": target_name
        }
        self.validation_data["nodes"].append(node_data)
        self.log(f"Node: {node_name}, children: {children_count}")

    def _parse_material_chunk(self, data: bytes):
        # Implementa il parsing del materiale
        # Simile a _parse_node_chunk ma con i campi specifici del materiale
        position = 0

        # Nome del materiale
        material_name = ""
        while data[position] != 0:
            material_name += chr(data[position])
            position += 1
        position += 1  # Salta il terminatore null

        # Leggi i colori e le proprietà
        emission = struct.unpack("<3f", data[position:position + 12])
        position += 12

        albedo = struct.unpack("<3f", data[position:position + 12])
        position += 12

        roughness = struct.unpack("<f", data[position:position + 4])[0]
        position += 4

        metalness = struct.unpack("<f", data[position:position + 4])[0]
        position += 4

        alpha = struct.unpack("<f", data[position:position + 4])[0]
        position += 4

        # Leggi i nomi delle texture
        texture_names = []
        for _ in range(5):  # albedo, normal, height, roughness, metalness
            texture_name = ""
            while position < len(data) and data[position] != 0:
                texture_name += chr(data[position])
                position += 1
            position += 1  # Salta il terminatore null
            texture_names.append(texture_name)

        # Aggiungi ai dati di validazione
        material_data = {
            "name": material_name,
            "emission": emission,
            "albedo": albedo,
            "roughness": roughness,
            "metalness": metalness,
            "alpha": alpha,
            "textures": {
                "albedo": texture_names[0],
                "normal": texture_names[1],
                "height": texture_names[2],
                "roughness": texture_names[3],
                "metalness": texture_names[4]
            }
        }
        self.validation_data["materials"].append(material_data)
        self.log(f"Material: {material_name}")

    def _parse_mesh_chunk(self, data: bytes):
        # Implementa il parsing della mesh
        # Simile ma più complesso a causa di vertici, facce, ecc.
        # Questa è una versione semplificata
        position = 0

        # Nome della mesh
        mesh_name = ""
        while data[position] != 0:
            mesh_name += chr(data[position])
            position += 1
        position += 1

        # Matrice
        matrix = struct.unpack("<16f", data[position:position + 64])
        position += 64

        # Numero di figli
        children_count = struct.unpack("<I", data[position:position + 4])[0]
        position += 4

        # Target node
        target_name = ""
        while position < len(data) and data[position] != 0:
            target_name += chr(data[position])
            position += 1
        position += 1

        # Sottotipo
        subtype = data[position]
        position += 1

        # Nome del materiale
        material_name = ""
        while position < len(data) and data[position] != 0:
            material_name += chr(data[position])
            position += 1
        position += 1

        # Raggio della bounding sphere
        radius = struct.unpack("<f", data[position:position + 4])[0]
        position += 4

        # BBox min e max
        bbox_min = struct.unpack("<3f", data[position:position + 12])
        position += 12
        bbox_max = struct.unpack("<3f", data[position:position + 12])
        position += 12

        # Flag fisica
        has_physics = data[position]
        position += 1

        # Se ci sono dati fisici, saltali (o parsali se necessario)
        if has_physics:
            # Questa è una semplificazione, dovresti adattarla ai dati effettivi
            position += 64  # Dimensione approssimativa dell'header di fisica

            # Leggi eventuali hull personalizzati
            nr_hulls = struct.unpack("<I", data[position - 8:position - 4])[0]
            for _ in range(nr_hulls):
                # Per ogni hull, leggi vertici e facce
                nr_vertices = struct.unpack("<I", data[position:position + 4])[0]
                position += 4
                nr_faces = struct.unpack("<I", data[position:position + 4])[0]
                position += 4
                centroid = struct.unpack("<3f", data[position:position + 12])
                position += 12

                # Salta i vertici
                position += nr_vertices * 12  # 3 float per vertice

                # Salta le facce
                position += nr_faces * 12  # 3 uint per faccia

        # Numero di LOD
        lod_count = struct.unpack("<I", data[position:position + 4])[0]
        position += 4

        # Dati per ogni LOD
        lods_data = []
        for lod in range(lod_count):
            # Numero di vertici e facce
            vertex_count = struct.unpack("<I", data[position:position + 4])[0]
            position += 4
            face_count = struct.unpack("<I", data[position:position + 4])[0]
            position += 4

            # Salta i dati dei vertici
            position += vertex_count * 24  # Dimensione approssimativa per vertice

            # Salta le facce
            position += face_count * 12  # 3 uint per faccia

            lods_data.append({
                "vertex_count": vertex_count,
                "face_count": face_count
            })

        # Aggiungi ai dati di validazione
        mesh_data = {
            "name": mesh_name,
            "matrix": matrix,
            "children_count": children_count,
            "target": target_name,
            "subtype": subtype,
            "material": material_name,
            "radius": radius,
            "bbox_min": bbox_min,
            "bbox_max": bbox_max,
            "has_physics": has_physics == 1,
            "lods": lods_data
        }
        self.validation_data["meshes"].append(mesh_data)
        self.log(f"Mesh: {mesh_name}, LODs: {lod_count}")

    def _parse_light_chunk(self, data: bytes):
        # Implementa il parsing della luce
        position = 0

        # Nome della luce
        light_name = ""
        while data[position] != 0:
            light_name += chr(data[position])
            position += 1
        position += 1

        # Matrice
        matrix = struct.unpack("<16f", data[position:position + 64])
        position += 64

        # Numero di figli
        children_count = struct.unpack("<I", data[position:position + 4])[0]
        position += 4

        # Target node
        target_name = ""
        while position < len(data) and data[position] != 0:
            target_name += chr(data[position])
            position += 1
        position += 1

        # Sottotipo
        subtype = data[position]
        position += 1

        # Colore
        color = struct.unpack("<3f", data[position:position + 12])
        position += 12

        # Raggio
        radius = struct.unpack("<f", data[position:position + 4])[0]
        position += 4

        # Direzione
        direction = struct.unpack("<3f", data[position:position + 12])
        position += 12

        # Cutoff
        cutoff = struct.unpack("<f", data[position:position + 4])[0]
        position += 4

        # Spot exponent
        spot_exponent = struct.unpack("<f", data[position:position + 4])[0]
        position += 4

        # Cast shadows
        cast_shadows = data[position]
        position += 1

        # Volumetric
        volumetric = data[position]
        position += 1

        # Aggiungi ai dati di validazione
        light_data = {
            "name": light_name,
            "matrix": matrix,
            "children_count": children_count,
            "target": target_name,
            "subtype": subtype,
            "color": color,
            "radius": radius,
            "direction": direction,
            "cutoff": cutoff,
            "spot_exponent": spot_exponent,
            "cast_shadows": cast_shadows == 1,
            "volumetric": volumetric == 1
        }
        self.validation_data["lights"].append(light_data)
        self.log(f"Light: {light_name}, type: {LightSubtype(subtype).name}")