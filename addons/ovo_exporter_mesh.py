"""
ovo_exporter_mesh.py
Gestisce le operazioni relative alle mesh per l'esportatore OVO.
Separa la logica di processamento delle mesh dal core dell'esportatore.
"""

import math
import struct
import bmesh
import bpy
import mathutils

# Importa le classi di supporto
try:
    # Per quando eseguito come addon
    from .ovo_types import ChunkType, HullType
    from .ovo_packer import OVOPacker
except ImportError:
    # Per quando eseguito direttamente
    from ovo_types import ChunkType, HullType
    from ovo_packer import OVOPacker

class OVOMeshManager:
    """
    Classe che gestisce il processamento delle mesh per l'esportatore OVO.
    Contiene metodi per la manipolazione e la conversione dei dati della mesh.
    """

    def __init__(self, packer):
        """
        Inizializza il gestore delle mesh.
        
        Args:
            packer (OVOPacker): Istanza del packer per serializzare i dati
        """
        self.packer = packer
    
    def process_mesh_geometry(self, mesh, bm, uv_layer):
        """
        Processa la geometria della mesh e prepara i dati per l'esportazione.
        
        Args:
            mesh: Mesh Blender da processare
            bm: BMesh già creato dalla mesh
            uv_layer: Layer UV da utilizzare
            
        Returns:
            tuple: (vertices_data, face_indices, vertex_count, face_count)
                vertices_data: Lista di tuple (posizione, normale, uv, tangente, sign)
                face_indices: Lista di indici che formano le facce triangolate
                vertex_count: Numero di vertici
                face_count: Numero di facce triangolate
        """
        # Ottieni i poly_lstart per calcolare gli indici dei loop
        poly_lstart = [p.loop_start for p in mesh.polygons]
        
        # Calcolo delle tangenti con gestione eccezioni
        def safe_calc_tangents(src_mesh):
            """
            Restituisce (loop_tangent, loop_sign) anche se la mesh contiene n-gon.
            La numerazione dei loop rimane identica a src_mesh.loops.
            """
            import bmesh
            # copia in memoria – non tocca la mesh originale
            mesh_copy = src_mesh.copy()

            bm_calc = bmesh.new()
            bm_calc.from_mesh(mesh_copy)
            bmesh.ops.triangulate(bm_calc, faces=bm_calc.faces)
            bm_calc.to_mesh(mesh_copy)
            bm_calc.free()

            mesh_copy.calc_tangents()                # ora non lancia eccezioni
            loop_tan  = [l.tangent.copy()   for l in mesh_copy.loops]
            loop_sign = [l.bitangent_sign   for l in mesh_copy.loops]

            bpy.data.meshes.remove(mesh_copy)        # pulizia
            return loop_tan, loop_sign

        # Calculate tangents safely
        loop_tangent = []
        loop_sign = []
        try:
            # Try to calculate tangents directly
            mesh.calc_tangents()
            loop_tangent = [l.tangent.copy() for l in mesh.loops]
            loop_sign = [l.bitangent_sign for l in mesh.loops]
        except Exception as e:
            print(f"      - mesh.calc_tangents() fallito: {str(e)}")
            print("      - Uso fallback sicuro")
            try:
                # Use the safe method
                loop_tangent, loop_sign = safe_calc_tangents(mesh)
            except Exception as e:
                print(f"      - Anche il fallback è fallito: {str(e)}")
                # Create default values if both methods fail
                print("      - Utilizzo valori di default per tangenti")
                for _ in range(len(mesh.loops)):
                    loop_tangent.append(mathutils.Vector((1.0, 0.0, 0.0)))
                    loop_sign.append(1.0)
        
        # Lista per i dati dei vertici e indici delle facce
        vertices_data = []  # [posizione, normale, uv, tangente, sign]
        face_indices = []   # Indici per le facce triangolate
        face_vertex_map = {}  # Mappa per ricordare quali vertici corrispondono a quali facce
        
        # Processamento delle facce originali
        print("      - Processando le facce originali per vertici e normali di faccia")
        for face_idx, face in enumerate(bm.faces):
            # Calcola la normale della faccia (non quella interpolata ai vertici)
            face_normal = face.normal.normalized()
            
            # Per ogni vertice in questa faccia
            for loop_idx, loop in enumerate(face.loops):
                vert_idx = loop.vert.index
                pos = loop.vert.co
                uv = loop[uv_layer].uv if uv_layer else mathutils.Vector((0.0, 0.0))

                # Sicurezza per l'indice del loop
                mesh_loop_index = poly_lstart[face_idx] + loop_idx if face_idx < len(poly_lstart) else 0
                
                # Controlla se il mesh_loop_index è valido
                if mesh_loop_index < len(loop_tangent):
                    bl_tangent = loop_tangent[mesh_loop_index]
                    sign = loop_sign[mesh_loop_index]
                else:
                    # Fallback in caso di problemi con l'indice
                    bl_tangent = mathutils.Vector((1.0, 0.0, 0.0))
                    sign = 1.0

                # Trasformazioni assi
                transformed_pos  = mathutils.Vector((pos.x, pos.z, -pos.y))
                transformed_norm = mathutils.Vector((face_normal.x, face_normal.z, -face_normal.y)).normalized()
                transformed_tan  = mathutils.Vector((bl_tangent.x, bl_tangent.z, -bl_tangent.y)).normalized()

                # Crea un indice unico per questo vertice nella faccia corrente
                vertex_idx = len(vertices_data)
                vertices_data.append((transformed_pos, transformed_norm, uv, transformed_tan, sign))
                face_vertex_map[(face_idx, vert_idx)] = vertex_idx
        
        # Triangolazione manuale delle facce
        print("      - Triangolazione manuale delle facce")
        face_count = 0
        for face_idx, face in enumerate(bm.faces):
            # Se la faccia ha 4 vertici (quad)
            if len(face.verts) == 4:
                # Indici dei vertici nella lista vertices_data
                v_indices = [face_vertex_map.get((face_idx, v.index), 0) for v in face.verts]
                
                # Triangola la faccia quad in modo coerente (0,1,2) e (0,2,3)
                face_indices.extend([v_indices[0], v_indices[1], v_indices[2]])
                face_indices.extend([v_indices[0], v_indices[2], v_indices[3]])
                face_count += 2  # Aggiungiamo 2 triangoli
            elif len(face.verts) == 3:
                # Per le facce che sono già triangoli, usa direttamente i loro indici
                v_indices = [face_vertex_map.get((face_idx, v.index), 0) for v in face.verts]
                face_indices.extend(v_indices)
                face_count += 1  # Aggiungiamo 1 triangolo
            else:
                # Per facce con più di 4 vertici (n-gon)
                # Usa una triangolazione a ventaglio dal primo vertice
                v0_idx = face_vertex_map.get((face_idx, face.verts[0].index), 0)
                for i in range(1, len(face.verts) - 1):
                    v1_idx = face_vertex_map.get((face_idx, face.verts[i].index), 0)
                    v2_idx = face_vertex_map.get((face_idx, face.verts[i+1].index), 0)
                    face_indices.extend([v0_idx, v1_idx, v2_idx])
                    face_count += 1  # Aggiungiamo 1 triangolo
        
        # Restituisci i dati elaborati
        vertex_count = len(vertices_data)
        print(f"      - Vertici: {vertex_count}")
        print(f"      - Facce triangolate: {face_count}")
        
        
        
        # Lista per i dati dei vertici e indici delle facce
        vertices_data = []  # [posizione, normale, uv, tangente, sign]
        face_indices = []   # Indici per le facce triangolate
        face_vertex_map = {}  # Mappa per ricordare quali vertici corrispondono a quali facce
        
        # Processamento delle facce originali
        print("      - Processando le facce originali per vertici e normali di faccia")
        for face_idx, face in enumerate(bm.faces):
            # Calcola la normale della faccia (non quella interpolata ai vertici)
            face_normal = face.normal.normalized()
            
            # Per ogni vertice in questa faccia
            for loop_idx, loop in enumerate(face.loops):
                vert_idx = loop.vert.index
                pos = loop.vert.co
                uv = loop[uv_layer].uv if uv_layer else mathutils.Vector((0.0, 0.0))

                mesh_loop_index = poly_lstart[face_idx] + loop_idx
                if mesh_loop_index < len(loop_tangent):
                    bl_tangent = loop_tangent[mesh_loop_index]
                    sign = loop_sign[mesh_loop_index]
                else:
                    # Fallback in caso di problemi con l'indice
                    bl_tangent = mathutils.Vector((1.0, 0.0, 0.0))
                    sign = 1.0

                # Trasformazioni assi
                transformed_pos  = mathutils.Vector((pos.x, pos.z, -pos.y))
                transformed_norm = mathutils.Vector((face_normal.x, face_normal.z, -face_normal.y)).normalized()
                transformed_tan  = mathutils.Vector((bl_tangent.x, bl_tangent.z, -bl_tangent.y)).normalized()

                # Crea un indice unico per questo vertice nella faccia corrente
                vertex_idx = len(vertices_data)
                vertices_data.append((transformed_pos, transformed_norm, uv, transformed_tan, sign))
                face_vertex_map[(face_idx, vert_idx)] = vertex_idx
        
        # Triangolazione manuale delle facce
        print("      - Triangolazione manuale delle facce")
        face_count = 0
        for face_idx, face in enumerate(bm.faces):
            # Se la faccia ha 4 vertici (quad)
            if len(face.verts) == 4:
                # Indici dei vertici nella lista vertices_data
                v_indices = [face_vertex_map.get((face_idx, v.index), 0) for v in face.verts]
                
                # Triangola la faccia quad in modo coerente (0,1,2) e (0,2,3)
                face_indices.extend([v_indices[0], v_indices[1], v_indices[2]])
                face_indices.extend([v_indices[0], v_indices[2], v_indices[3]])
                face_count += 2  # Aggiungiamo 2 triangoli
            elif len(face.verts) == 3:
                # Per le facce che sono già triangoli, usa direttamente i loro indici
                v_indices = [face_vertex_map.get((face_idx, v.index), 0) for v in face.verts]
                face_indices.extend(v_indices)
                face_count += 1  # Aggiungiamo 1 triangolo
            else:
                # Per facce con più di 4 vertici (n-gon)
                # Usa una triangolazione a ventaglio dal primo vertice
                v0_idx = face_vertex_map.get((face_idx, face.verts[0].index), 0)
                for i in range(1, len(face.verts) - 1):
                    v1_idx = face_vertex_map.get((face_idx, face.verts[i].index), 0)
                    v2_idx = face_vertex_map.get((face_idx, face.verts[i+1].index), 0)
                    face_indices.extend([v0_idx, v1_idx, v2_idx])
                    face_count += 1  # Aggiungiamo 1 triangolo
        
        # Restituisci i dati elaborati
        vertex_count = len(vertices_data)
        print(f"      - Vertici: {vertex_count}")
        print(f"      - Facce triangolate: {face_count}")
        
        return vertices_data, face_indices, vertex_count, face_count

    def write_mesh_data(self, chunk_data, vertices_data, face_indices, vertex_count, face_count):
        """
        Scrive i dati della mesh nel chunk.
        
        Args:
            chunk_data: Buffer di dati esistente
            vertices_data: Lista di tuple (posizione, normale, uv, tangente, sign)
            face_indices: Lista di indici che formano le facce triangolate
            vertex_count: Numero di vertici
            face_count: Numero di facce triangolate
        
        Returns:
            bytes: Buffer aggiornato con i dati della mesh
        """
        # Scrivi numero di vertici e facce
        chunk_data += struct.pack('I', vertex_count)
        chunk_data += struct.pack('I', face_count)
        
        # Scrivi i dati dei vertici
        print(f"      - Scrittura {vertex_count} vertici")
        for pos, norm, uv, tan, sign in vertices_data:
            chunk_data += self.packer.pack_vector3(pos)
            chunk_data += self.packer.pack_normal(norm)
            chunk_data += self.packer.pack_uv(uv)
            chunk_data += self.packer.pack_tangent(tan)

        # Scrivi gli indici delle facce
        print(f"      - Scrittura {face_count} facce triangolate")
        for i in range(0, len(face_indices), 3):
            # Assicurati di non superare i limiti dell'array
            if i + 2 < len(face_indices):
                for j in range(3):
                    chunk_data += struct.pack('I', face_indices[i + j])
        
        return chunk_data

    def get_box_radius(self, vertices):
        # NUOVO CALCOLO DEL BOUNDING BOX E RAGGIO IN OBJECT COORDINATES
        # Calcola bounding box e raggio direttamente dai vertici della mesh in coordinate locali
        min_box = mathutils.Vector((float('inf'), float('inf'), float('inf')))
        max_box = mathutils.Vector((float('-inf'), float('-inf'), float('-inf')))
        max_distance_squared = 0.0
        
        # Trova min e max per ogni asse e la distanza massima dal centro
        for v in vertices:
            # Calcola il bounding box
            position = v.co
            # Converti coordinate (x, y, z) a (x, z, -y) per il formato OVO
            pos_transformed = mathutils.Vector((position.x, position.z, -position.y))
            
            min_box.x = min(min_box.x, pos_transformed.x)
            min_box.y = min(min_box.y, pos_transformed.y)
            min_box.z = min(min_box.z, pos_transformed.z)
            
            max_box.x = max(max_box.x, pos_transformed.x)
            max_box.y = max(max_box.y, pos_transformed.y)
            max_box.z = max(max_box.z, pos_transformed.z)
            
            # Calcola il raggio come distanza massima dal centro
            dist_squared = pos_transformed.length_squared
            max_distance_squared = max(max_distance_squared, dist_squared)
        
        # Il raggio è la radice quadrata della distanza massima al quadrato
        radius = math.sqrt(max_distance_squared)

        print(f"      - Bounding radius (object space): {radius:.4f}")
        print(f"      - Bounding box min (object space): ({min_box.x:.4f}, {min_box.y:.4f}, {min_box.z:.4f})")
        print(f"      - Bounding box max (object space): ({max_box.x:.4f}, {max_box.y:.4f}, {max_box.z:.4f})")
        return radius, min_box, max_box
    
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
        print(f"      - LOD count: {lod_count}")

        # Process each LOD level
        for lod_index, bm in enumerate(lod_meshes):
            print(f"      - Processing LOD {lod_index + 1}/{lod_count}")

            # Convertiamo il BMesh in una mesh temporanea di Blender per calcolare le tangenti
            temp_mesh = bpy.data.meshes.new(f"temp_lod_{lod_index}")
            bm.to_mesh(temp_mesh)
            
            # Assicuriamoci che la mesh abbia delle tangenti valide creando un BMesh pulito
            import bmesh
            clean_bm = bmesh.new()
            # Crea una copia della mesh per evitare problemi con from_mesh
            temp_mesh_copy = temp_mesh.copy()
            clean_bm.from_mesh(temp_mesh_copy)
            
            # Get UV layer
            uv_layer = clean_bm.loops.layers.uv.active
            if uv_layer:
                print(f"      - LOD {lod_index + 1}: UV layer found: '{temp_mesh.uv_layers.active.name if temp_mesh.uv_layers.active else 'default'}'")
            else:
                print(f"      - LOD {lod_index + 1}: WARNING - No UV layer found")
            
            # Processa la geometria della mesh
            vertices_data, face_indices, vertex_count, face_count = self.process_mesh_geometry(temp_mesh, clean_bm, uv_layer)
            
            # Scrivi i dati della mesh nel chunk
            chunk_data = self.write_mesh_data(chunk_data, vertices_data, face_indices, vertex_count, face_count)
            
            # Cleanup delle mesh temporanee
            clean_bm.free()
            bpy.data.meshes.remove(temp_mesh_copy)
            bpy.data.meshes.remove(temp_mesh)

        return chunk_data