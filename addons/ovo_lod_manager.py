# ================================================================
# LOD MANAGER
# ================================================================
# Manages Level of Detail (LOD) generation for the OVO exporter.
# Generates simplified mesh representations based on face count
# thresholds using Blender's decimate modifier and triangulation.
# ================================================================

# --------------------------------------------------------
# IMPORTS
# --------------------------------------------------------
import bpy
import bmesh
from mathutils import Vector

try:
    from .ovo_log import log
except ImportError:
    from ovo_log import log

# --------------------------------------------------------
# LOD Manager
# --------------------------------------------------------
class OVOLodManager:
    """
    Manages automatic generation of LOD (Level of Detail) meshes
    using face-count analysis and Blender's Decimate modifier.

    If the mesh exceeds a configured face threshold, multiple simplified
    versions (LODs) are generated and exported.
    """

    def __init__(self):
        """
        Initializes the LOD Manager with face count thresholds
        and decimation ratios for generating multiple LODs.
        """
        self.LOD_FACE_THRESHOLD = 300000  # Threshold for multi-LOD generation
        self.LOD_RATIOS = [1.0, 0.8, 0.5, 0.3, 0.1]  # Ratios for LOD levels

    # --------------------------------------------------------
    # Should Generate Multi-LOD
    # --------------------------------------------------------
    def should_generate_multi_lod(self, obj):
        """
        Determines if multiple LODs should be generated for the object.

        Args:
            obj: Blender object to analyze

        Returns:
            bool: True if multi-LOD should be generated, False otherwise
        """
        # Get the mesh data
        depsgraph = bpy.context.evaluated_depsgraph_get()
        obj_eval = obj.evaluated_get(depsgraph)
        mesh = obj_eval.to_mesh()

        # Create BMesh for triangulation
        bm = bmesh.new()
        bm.from_mesh(mesh)
        bmesh.ops.triangulate(bm, faces=bm.faces)

        face_count = len(bm.faces)

        # Clean up
        bm.free()
        obj_eval.to_mesh_clear()

        log(f"Face count: {face_count}", category="MESH", indent=2)
        return face_count > self.LOD_FACE_THRESHOLD

    def generate_lod_meshes(self, obj):
        """
        Generates LOD meshes for the given object.

        Args:
            obj: Blender object to process

        Returns:
            list: List of BMesh objects representing different LOD levels
        """
        if not self.should_generate_multi_lod(obj):
            # If below threshold, return a single LOD
            log("Generating single LOD (below threshold)", category="MESH", indent=1)
            return self._generate_single_lod(obj)

        # Generate multiple LODs
        log("Generating multiple LODs", category="MESH", indent=1)
        return self._generate_multiple_lods(obj)

    def _generate_single_lod(self, obj):
        """
        Generates a single LOD for the object.

        Args:
            obj: Blender object to process

        Returns:
            list: List containing a single BMesh object
        """
        depsgraph = bpy.context.evaluated_depsgraph_get()
        obj_eval = obj.evaluated_get(depsgraph)
        mesh = obj_eval.to_mesh()

        bm = bmesh.new()
        bm.from_mesh(mesh)
        bmesh.ops.triangulate(bm, faces=bm.faces)

        # Return a list with a single LOD
        return [bm]

    def _generate_multiple_lods(self, obj):
        """
        Generates multiple LODs for the object using Blender's Decimate modifier.

        Args:
            obj: Blender object to process

        Returns:
            list: List of BMesh objects representing different LOD levels
        """
        lod_meshes = []

        # Create a temporary collection to hold our LOD objects
        temp_collection = bpy.data.collections.new("_temp_lod_collection")
        bpy.context.scene.collection.children.link(temp_collection)

        try:
            # Make a copy of the original object for each LOD level
            for i, ratio in enumerate(self.LOD_RATIOS):
                # For the highest detail LOD (ratio=1.0), just use the original mesh
                if ratio == 1.0:
                    depsgraph = bpy.context.evaluated_depsgraph_get()
                    obj_eval = obj.evaluated_get(depsgraph)
                    mesh = obj_eval.to_mesh()

                    bm = bmesh.new()
                    bm.from_mesh(mesh)
                    bmesh.ops.triangulate(bm, faces=bm.faces)

                    # Make sure we copy over UV layers from the original mesh
                    if len(mesh.uv_layers) > 0:
                        uv_name = mesh.uv_layers.active.name
                        uv_layer = bm.loops.layers.uv.new(uv_name)

                    log(f"LOD ratio {ratio:.2f}: {len(bm.faces)} faces (original)", category="MESH", indent=2)
                    lod_meshes.append(bm)
                    continue

                # Create a copy of the object
                lod_obj = obj.copy()
                lod_obj.data = obj.data.copy()
                lod_obj.name = f"{obj.name}_LOD_{i}"
                temp_collection.objects.link(lod_obj)

                # Add a Decimate modifier
                decimate_mod = lod_obj.modifiers.new(name="Decimate", type='DECIMATE')
                decimate_mod.ratio = ratio
                decimate_mod.use_collapse_triangulate = True

                # Apply the modifier
                bpy.context.view_layer.objects.active = lod_obj
                bpy.ops.object.modifier_apply(modifier="Decimate")

                # Create a BMesh from the decimated object
                bm = bmesh.new()
                bm.from_mesh(lod_obj.data)
                bmesh.ops.triangulate(bm, faces=bm.faces)

                # Make sure we copy over UV layers
                if len(lod_obj.data.uv_layers) > 0:
                    uv_name = lod_obj.data.uv_layers.active.name
                    uv_layer = bm.loops.layers.uv.new(uv_name)

                    # Copy UV data from the mesh to the bmesh
                    for face in bm.faces:
                        for loop in face.loops:
                            mesh_loop_index = loop.index
                            if mesh_loop_index < len(lod_obj.data.loops):
                                mesh_loop = lod_obj.data.loops[mesh_loop_index]
                                if mesh_loop.vertex_index < len(lod_obj.data.uv_layers.active.data):
                                    uv_data = lod_obj.data.uv_layers.active.data[mesh_loop.index]
                                    loop[uv_layer].uv = uv_data.uv

                log(f"LOD ratio {ratio:.2f}: {len(bm.faces)} faces", category="MESH", indent=2)
                lod_meshes.append(bm)

                # Remove the LOD object
                bpy.data.objects.remove(lod_obj)

        finally:
            # Clean up
            try:
                # Remove the temporary collection
                bpy.data.collections.remove(temp_collection)
            except:
                pass

        return lod_meshes

    # --------------------------------------------------------
    # Cleanup LOD Meshes
    # --------------------------------------------------------
    def cleanup_lod_meshes(self, lod_meshes):
        """
        Cleans up the LOD meshes.

        Args:
            lod_meshes: List of BMesh objects to clean up
        """
        for bm in lod_meshes:
            bm.free()