# --------------------------------------------------------
#  OVO IMPORTER BUILDER
# --------------------------------------------------------
# This module converts NodeRecord objects (parsed from the .ovo file)
# into actual Blender objects. It delegates object creation to dedicated
# factories:
#   - MeshFactory for MESH nodes,
#   - LightFactory for LIGHT nodes,
#   - NodeFactory for generic nodes.
#
# It then builds the parent–child hierarchy, creates a root if needed,
# and applies final transformations.
# ================================================================
import math

import bpy
import mathutils

from .ovo_types import LightType
from .ovo_mesh_factory import MeshFactory
from .ovo_light_factory import LightFactory
from .ovo_node_factory import NodeFactory

class OVOSceneBuilder:
    """
    Builds a Blender scene from parsed importer data.

    Attributes:
        node_records (list): List of NodeRecord objects (for NODE, MESH, LIGHT).
        materials (dict): Dictionary mapping material names to OVOMaterial objects.
        texture_directory (str): Base folder to search for texture files.
        flip_textures (bool): Whether to flip textures vertically.
        record_to_object (dict): Maps each NodeRecord to its created Blender object.
    """

    def __init__(self, node_records, materials, texture_directory, flip_textures=True):
        """
        Initialize with parsed data.

        :param node_records: A list of NodeRecord objects containing parsed node information.
        :param materials: A dictionary of material data keyed by material name.
        :param texture_directory: The directory where texture files are located.
        :param flip_textures: Whether to flip textures vertically.
        """
        self.node_records = node_records
        self.materials = materials
        self.texture_directory = texture_directory
        self.flip_textures = flip_textures
        self.record_to_object = {}

    def build_scene(self):
        """
        Main entry point to build the Blender scene.

        Steps:
          1) For each NodeRecord, create an object using the appropriate factory.
          2) Build parent–child relationships using a stack-based approach.
          3) Establish a [root] node if multiple top-level nodes exist.
          4) Apply final transformations (transpose, rotations, quaternion corrections).
        """
        # Create a Blender object for each node record using factories.
        for rec in self.node_records:
            if rec.node_type == "MESH":
                obj = MeshFactory.create(rec, self.materials, self.texture_directory, flip_textures=self.flip_textures)
            elif rec.node_type == "LIGHT":
                obj = LightFactory.create(rec)
            else:
                # Use NodeFactory for generic nodes.
                obj = NodeFactory.create(rec)
            self.record_to_object[rec] = obj

        # Build the hierarchy (parent–child relationships).
        self._build_hierarchy()

        # Establish a root node if more than one top-level node exists.
        self._establish_root_node()

        # Apply final transformations for proper orientation.
        self._apply_transformations()

        print("[OVOSceneBuilder] Scene build complete!")
        print(f"[OVOSceneBuilder] Textures {'flipped' if self.flip_textures else 'not flipped'} during import")

    # The _build_hierarchy, _establish_root_node, and _apply_transformations
    # methods remain unchanged as they deal with structuring and transforming
    # the scene rather than object creation.
    # --------------------------------------------------
    #  Build Hierarchy
    # --------------------------------------------------
    def _build_hierarchy(self):
        """
        Creates parent-child relationships among the NodeRecord objects.

        Uses a stack-based approach:
          - Iterates over all NodeRecord objects.
          - Assigns a parent for each child based on the 'children_count'.
          - Decreases the parent's children_count as children are assigned.
        """
        stack = []
        for rec in self.node_records:
            while stack and stack[-1].children_count == 0:
                stack.pop()

            if stack:
                parent_rec = stack[-1]
                rec_obj = self.record_to_object[rec]
                par_obj = self.record_to_object[parent_rec]
                rec_obj.parent = par_obj
                parent_rec.children_count -= 1

            if rec.children_count > 0:
                stack.append(rec)

    # --------------------------------------------------
    #  Establish Root Node
    # --------------------------------------------------
    def _establish_root_node(self):
        """
        Checks if multiple top-level nodes exist. If so, creates a fake "[root]"
        empty object and parents all top-level objects to it.
        """
        top_records = [rec for rec in self.node_records if not self.record_to_object[rec].parent]
        if len(top_records) > 1:
            print("[OVOSceneBuilder] Multiple top-level nodes detected; creating [root].")
            root_obj = bpy.data.objects.new("[root]", None)
            root_obj.empty_display_type = 'PLAIN_AXES'
            bpy.context.collection.objects.link(root_obj)

            for rec in top_records:
                self.record_to_object[rec].parent = root_obj

    # --------------------------------------------------
    #  Apply Final Transformations
    # --------------------------------------------------
    def _apply_transformations(self):
        """
        Finalizes the scene by applying the correct object transformations.
        This updated version addresses issues with mesh rotation and light orientation.
        """
        def log_info(message, indent=0):
            prefix = "  " * indent
            print(f"{prefix}{message}")

        log_info("[OVOImporter] Applying transformations.")

        for rec in self.node_records:
            if rec.name == "[root]":
                log_info("Skipping [root] node.", indent=1)
                continue

            obj = self.record_to_object.get(rec)
            if not obj:
                log_info(f"Node '{rec.name}' has no associated Blender object. Skipping.", indent=1)
                continue

            # Convert the raw matrix to a Blender matrix
            mat = mathutils.Matrix(rec.raw_matrix)
            mat.transpose()  # Convert from row-major to column-major format
            
            # Apply an extra rotation for objects parented to the [root]
            if obj.parent and obj.parent.name == "[root]":
                conv_90_x = mathutils.Matrix([
                    [1, 0, 0, 0],
                    [0, 0, -1, 0],
                    [0, 1, 0, 0],
                    [0, 0, 0, 1]
                ])
                mat = conv_90_x @ mat
                log_info(f"Extra +90° X rotation applied to '{rec.name}' because parent is [root].", indent=1)

            # Set the basic transformation matrix for all objects
            obj.matrix_basis = mat

            if rec.node_type == "MESH":
                # For meshes, we'll rotate vertices by -90 degrees around X instead of +90
                # This should counter the excess rotation
                if hasattr(obj, 'data') and obj.data is not None and hasattr(obj.data, 'vertices'):
                    mesh = obj.data
                    
                    # Create a -90-degree rotation matrix around X axis (counter-rotation)
                    rot_x_minus_90 = mathutils.Matrix.Rotation(math.radians(-90), 4, 'X')
                    
                    log_info(f"Applying counter-rotation to vertices for mesh '{rec.name}'", indent=1)
                    
                    # Apply rotation to each vertex
                    for vertex in mesh.vertices:
                        # Create a 4D vector with w=1
                        v = mathutils.Vector((vertex.co.x, vertex.co.y, vertex.co.z, 1.0))
                        
                        # Apply the counter-rotation
                        v_rot = rot_x_minus_90 @ v
                        
                        # Update the vertex coordinates
                        vertex.co.x = v_rot.x
                        vertex.co.y = v_rot.y
                        vertex.co.z = v_rot.z
                    
                    # Ensure the mesh updates
                    mesh.update()
                    log_info(f"Vertices transformed for mesh '{rec.name}'", indent=1)
                    
            elif rec.node_type == "LIGHT":
                # For lights, we'll handle directional and spot lights specially
                if rec.light_type in (LightType.DIRECTIONAL, LightType.SPOT):
                    if rec.light_quat:
                        # If we have a quaternion for the light direction, use it directly
                        log_info(f"Applying quaternion correction for light '{rec.name}'", indent=1)
                        obj.rotation_mode = 'QUATERNION'
                        obj.rotation_quaternion = rec.light_quat
                    else:
                        # If no quaternion, adjust Euler rotation
                        log_info(f"Adjusting Euler rotation for light '{rec.name}'", indent=1)
                        obj.rotation_mode = 'XYZ'
                        euler = obj.rotation_euler.copy()
                        # No adjustment needed since we're using the matrix as-is
                        obj.rotation_euler = euler
                else:
                    # For other light types, use matrix as-is
                    pass
            else:
                # For generic nodes, use matrix as-is
                pass

            # Log the final rotation for debugging
            if obj.rotation_mode == 'QUATERNION':
                log_info(f"Final rotation for '{rec.name}': Quaternion {obj.rotation_quaternion}", indent=1)
            else:
                final_euler = obj.rotation_euler
                x_deg = math.degrees(final_euler.x)
                y_deg = math.degrees(final_euler.y)
                z_deg = math.degrees(final_euler.z)
                log_info(f"Final rotation for '{rec.name}': X={x_deg:.2f}°, Y={y_deg:.2f}°, Z={z_deg:.2f}°", indent=1)