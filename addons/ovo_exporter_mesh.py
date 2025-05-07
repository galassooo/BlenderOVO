# ================================================================
# EXPORTER MESH MODULE
# ================================================================
# This module Handles mesh-related operations for the OVO exporter.
# Separates mesh processing logic from the core exporter.
# ================================================================

# --------------------------------------------------------
# IMPORTS
# --------------------------------------------------------
import math
import struct
import bmesh
import bpy
import mathutils

try:
    from .ovo_types import ChunkType, HullType
    from .ovo_packer import OVOPacker
    from .ovo_log import log
except ImportError:
    from ovo_types import ChunkType, HullType
    from ovo_packer import OVOPacker
    from ovo_log import log

# --------------------------------------------------------
# OVOMeshManager
# --------------------------------------------------------
class OVOMeshManager:
    """
    Class that manages mesh processing for the OVO exporter.
    Contains methods for mesh manipulation and data conversion.
    """

    def __init__(self, packer):
        """
        Initializes the mesh manager.
        
        Args:
            packer (OVOPacker): Instance of the packer to serialize data
        """
        self.packer = packer
    

    # --------------------------------------------------------
    # Calculate tangents in safe mode for n-gons
    # --------------------------------------------------------
    def safe_calc_tangents(self, src_mesh):
            """
            Returns (loop_tangent, loop_sign) even if the mesh contains n-gons.
            Loop numbering remains identical to src_mesh.loops.
            """
            import bmesh
            # memory copy - doesn't touch the original mesh
            mesh_copy = src_mesh.copy()

            bm_calc = bmesh.new()
            bm_calc.from_mesh(mesh_copy)
            bmesh.ops.triangulate(bm_calc, faces=bm_calc.faces)
            bm_calc.to_mesh(mesh_copy)
            bm_calc.free()

            mesh_copy.calc_tangents()                # now it won't throw exceptions
            loop_tan  = [l.tangent.copy()   for l in mesh_copy.loops]
            loop_sign = [l.bitangent_sign   for l in mesh_copy.loops]

            bpy.data.meshes.remove(mesh_copy)        # cleanup
            return loop_tan, loop_sign

    # --------------------------------------------------------
    # Write Mesh data
    # --------------------------------------------------------
    def write_mesh_data(self, chunk_data, vertices_data, face_indices, vertex_count, face_count):
        """
        Writes mesh data to the chunk.
        
        Args:
            chunk_data: Existing data buffer
            vertices_data: List of tuples (position, normal, uv, tangent, sign)
            face_indices: List of indices forming triangulated faces
            vertex_count: Number of vertices
            face_count: Number of triangulated faces
        
        Returns:
            bytes: Updated buffer with mesh data
        """
        # Write vertex and face counts
        chunk_data += struct.pack('I', vertex_count)
        chunk_data += struct.pack('I', face_count)
        
        # Write vertex data
        log(f"- Writing {vertex_count} vertices", category="MESH", indent=3)
        for pos, norm, uv, tan, sign in vertices_data:
            chunk_data += self.packer.pack_vector3(pos)
            chunk_data += self.packer.pack_normal(norm)
            chunk_data += self.packer.pack_uv(uv)
            chunk_data += self.packer.pack_tangent(tan)

        # Write face indices
        log(f"- Writing {face_count} triangulated faces", category="MESH", indent=3)
        for i in range(0, len(face_indices), 3):
            if i + 2 < len(face_indices):
                for j in range(3):
                    chunk_data += struct.pack('I', face_indices[i + j])
        
        return chunk_data

    # --------------------------------------------------------
    # Get bounding box and radius
    # --------------------------------------------------------
    def get_box_radius(self, vertices):
        """
        Calculate bounding box and radius in object coordinates.
        
        Args:
            vertices: Vertices of the mesh
            
        Returns:
            tuple: (radius, min_box, max_box)
        """
        # Calculate bounding box and radius directly from mesh vertices in local coordinates
        min_box = mathutils.Vector((float('inf'), float('inf'), float('inf')))
        max_box = mathutils.Vector((float('-inf'), float('-inf'), float('-inf')))
        max_distance_squared = 0.0
        
        # Find min and max for each axis and maximum distance from center
        for v in vertices:
            # Calculate bounding box
            position = v.co
            # Convert coordinates (x, y, z) to (x, z, -y) for OVO format
            pos_transformed = mathutils.Vector((position.x, position.z, -position.y))
            
            min_box.x = min(min_box.x, pos_transformed.x)
            min_box.y = min(min_box.y, pos_transformed.y)
            min_box.z = min(min_box.z, pos_transformed.z)
            
            max_box.x = max(max_box.x, pos_transformed.x)
            max_box.y = max(max_box.y, pos_transformed.y)
            max_box.z = max(max_box.z, pos_transformed.z)
            
            # Calculate radius as maximum distance from center
            dist_squared = pos_transformed.length_squared
            max_distance_squared = max(max_distance_squared, dist_squared)
        
        radius = math.sqrt(max_distance_squared)

        log(f"- Bounding radius (object space): {radius:.4f}", category="MESH", indent=3)
        log(f"- Bounding box min (object space): ({min_box.x:.4f}, {min_box.y:.4f}, {min_box.z:.4f})", category="MESH", indent=3)
        log(f"- Bounding box max (object space): ({max_box.x:.4f}, {max_box.y:.4f}, {max_box.z:.4f})", category="MESH", indent=3)
        return radius, min_box, max_box
    
    # --------------------------------------------------------
    # Write lod data
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

            # Convert BMesh to a temporary Blender mesh to calculate tangents
            temp_mesh = bpy.data.meshes.new(f"temp_lod_{lod_index}")
            bm.to_mesh(temp_mesh)
            
            # Make sure the mesh has valid tangents by creating a clean BMesh
            import bmesh
            clean_bm = bmesh.new()
            # Create a copy of the mesh to avoid problems with from_mesh
            temp_mesh_copy = temp_mesh.copy()
            clean_bm.from_mesh(temp_mesh_copy)
            
            # Get UV layer
            uv_layer = clean_bm.loops.layers.uv.active
            if uv_layer:
                log(f"- LOD {lod_index + 1}: UV layer found: '{temp_mesh.uv_layers.active.name if temp_mesh.uv_layers.active else 'default'}'", category="MESH", indent=4)
            else:
                log(f"- LOD {lod_index + 1}: WARNING - No UV layer found", category="WARNING", indent=4)
            
            # Process mesh geometry
            vertices_data, face_indices, vertex_count, face_count = self.process_mesh_geometry(temp_mesh, clean_bm, uv_layer)
            
            # Write mesh data to the chunk
            chunk_data = self.write_mesh_data(chunk_data, vertices_data, face_indices, vertex_count, face_count)
            
            # Cleanup temporary meshes
            clean_bm.free()
            bpy.data.meshes.remove(temp_mesh_copy)
            bpy.data.meshes.remove(temp_mesh)

        return chunk_data