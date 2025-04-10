# --------------------------------------------------------
#  OVO IMPORTER BUILDER
# --------------------------------------------------------
# This module converts NodeRecord objects (parsed from the .ovo file)
# into actual Blender objects. It handles:
#   1) Creation of Blender objects based on node type:
#        - Empty objects for generic nodes
#        - Mesh objects for MESH nodes (with geometry, UVs, and material assignments)
#        - Light objects for LIGHT nodes (setting type, color, energy, etc.)
#   2) Building the parent–child hierarchy using a stack-based approach.
#   3) Creating a root node if more than one top-level node exists.
#   4) Applying final transformations (e.g. matrix transposition and partial rotations).
# --------------------------------------------------------

import bpy
import mathutils

from .ovo_types import HullType, LightType


class OVOSceneBuilder:
    """
    Builds a Blender scene from parsed importer data.

    Attributes:
        node_records (list): List of NodeRecord objects (for NODE, MESH, LIGHT).
        materials (dict): Dictionary mapping material names to OVOMaterial objects.
        texture_directory (str): Base folder to search for texture files.
        record_to_object (dict): Maps each NodeRecord to its created Blender object.
    """

    def __init__(self, node_records, materials, texture_directory):
        """
        Initialize with parsed data.

        :param node_records: A list of NodeRecord objects containing parsed node information.
        :param materials: A dictionary of material data keyed by material name.
        :param texture_directory: The directory where texture files are located.
        """
        self.node_records = node_records
        self.materials = materials
        self.texture_directory = texture_directory
        self.record_to_object = {}  # Will map NodeRecord -> bpy.types.Object

    def build_scene(self):
        """
        Main entry point to build the Blender scene.

        Steps:
          1) For each NodeRecord:
              - Create an empty for NODE types.
              - Create a mesh for MESH types, including geometry, UVs, material, and physics.
              - Create a light for LIGHT types, setting proper properties.
          2) Build parent–child relationships using a stack approach.
          3) Create a root node if multiple top-level nodes exist.
          4) Apply final matrix transformations (transpose and rotations).
        """
        # Create a Blender object for each node record.
        for rec in self.node_records:
            if rec.node_type == "MESH":
                obj = self._create_mesh(rec)
            elif rec.node_type == "LIGHT":
                obj = self._create_light(rec)
            else:
                # Assume generic NODE
                obj = self._create_empty_node(rec)
            self.record_to_object[rec] = obj

        # Build the hierarchy (parent–child relationships).
        self._build_hierarchy()

        # Establish a root node if more than one top-level node exists.
        self._establish_root_node()

        # Apply final transformations for proper orientation.
        self._apply_transformations()

        print("[OVOSceneBuilder] Scene build complete!")

    # --------------------------------------------------
    #  Create Empty Node
    # --------------------------------------------------
    def _create_empty_node(self, rec):
        """
        Creates an Empty object in Blender for a node of type "NODE".

        :param rec: The NodeRecord with node_type "NODE".
        :return: The created Blender Empty object.
        """
        node_obj = bpy.data.objects.new(rec.name, None)
        node_obj.empty_display_type = 'PLAIN_AXES'
        node_obj.empty_display_size = 1.0

        # Link the object to the current collection if not already linked.
        if not node_obj.users_collection:
            bpy.context.collection.objects.link(node_obj)
        return node_obj

    # --------------------------------------------------
    #  Create Light Object
    # --------------------------------------------------
    def _create_light(self, rec):
        """
        Creates a Blender Light object for a node with node_type "LIGHT".

        Converts the numeric light type from the .ovo file to a Blender light type:
          - 0: POINT
          - 1: SUN
          - 2: SPOT
          - Otherwise, defaults to POINT.

        :param rec: The NodeRecord with node_type "LIGHT" and related light parameters.
        :return: The created Blender Light object.
        """
        if rec.light_type == 0:
            ldata = bpy.data.lights.new(rec.name, type='POINT')
        elif rec.light_type == 1:
            ldata = bpy.data.lights.new(rec.name, type='SUN')
        elif rec.light_type == 2:
            ldata = bpy.data.lights.new(rec.name, type='SPOT')
        else:
            ldata = bpy.data.lights.new(rec.name, type='POINT')

        # Set basic light properties.
        ldata.color = rec.color
        ldata.energy = rec.radius * 10
        ldata.use_shadow = bool(rec.shadow)

        # Specific settings for spot lights.
        if rec.light_type == 2:
            ldata.spot_size = rec.cutoff
            ldata.spot_blend = rec.spot_exponent / 10.0

        light_obj = bpy.data.objects.new(rec.name, ldata)
        if not light_obj.users_collection:
            bpy.context.collection.objects.link(light_obj)
        return light_obj

    # --------------------------------------------------
    #  Create Mesh Object
    # --------------------------------------------------
    def _create_mesh(self, rec):
        """
        Creates a Blender Mesh object for a node with node_type "MESH".

        This method:
          - Creates a new mesh, populates it with vertices and faces.
          - Creates a UV map if UV data is provided.
          - Assigns a material if rec.material_name is found in the materials dictionary.
          - Applies physics data if available.

        :param rec: The NodeRecord with node_type "MESH".
        :return: The created Blender Mesh object.
        """
        # Create an empty mesh if no geometry data is present.
        if not rec.vertices:
            mesh_data = bpy.data.meshes.new(rec.name)
        else:
            mesh_data = bpy.data.meshes.new(rec.name)
            mesh_data.from_pydata(rec.vertices, [], rec.faces)
            mesh_data.update()

            # Create UV map if the number of UVs matches the vertices.
            if len(rec.uvs) == len(rec.vertices) and rec.vertices:
                uv_layer = mesh_data.uv_layers.new(name="UVMap")
                for poly in mesh_data.polygons:
                    for loop_idx in range(poly.loop_start, poly.loop_start + poly.loop_total):
                        vert_idx = mesh_data.loops[loop_idx].vertex_index
                        uv_layer.data[loop_idx].uv = rec.uvs[vert_idx]

        mesh_obj = bpy.data.objects.new(rec.name, mesh_data)
        if not mesh_obj.users_collection:
            bpy.context.collection.objects.link(mesh_obj)

        # Assign material if available.
        if rec.material_name and rec.material_name in self.materials:
            ovo_mat = self.materials[rec.material_name]
            mat = self._create_blender_material(ovo_mat)
            if mat:
                if not mesh_obj.data.materials:
                    mesh_obj.data.materials.append(mat)
                else:
                    mesh_obj.data.materials[0] = mat

        # Apply physics data if available.
        if rec.physics_data:
            self._apply_physics(mesh_obj, rec.physics_data)

        return mesh_obj

    # --------------------------------------------------
    #  Material Creation
    # --------------------------------------------------
    def _create_blender_material(self, ovo_mat):
        """
        Converts an OVOMaterial object into a Blender Material.

        This method sets up the Principled BSDF node with basic properties.
        Texture loading logic can be added here if needed.

        :param ovo_mat: An OVOMaterial containing parsed material parameters.
        :return: The created Blender Material.
        """
        mat = bpy.data.materials.new(ovo_mat.name)
        mat.use_nodes = True

        # Find the Principled BSDF node.
        bsdf = None
        for node in mat.node_tree.nodes:
            if node.type == 'BSDF_PRINCIPLED':
                bsdf = node
                break
        if not bsdf:
            print(f"[OVOSceneBuilder] No Principled BSDF found in {ovo_mat.name}")
            return mat

        # Apply basic properties.
        bsdf.inputs["Base Color"].default_value = (*ovo_mat.base_color, 1.0)
        bsdf.inputs["Roughness"].default_value = ovo_mat.roughness
        bsdf.inputs["Metallic"].default_value = ovo_mat.metallic

        # Handle transparency.
        if ovo_mat.transparency < 1.0:
            mat.blend_method = 'BLEND'
            mat.shadow_method = 'HASHED'
            bsdf.inputs["Alpha"].default_value = ovo_mat.transparency

        # Apply emission if available.
        if "Emission" in bsdf.inputs:
            bsdf.inputs["Emission"].default_value = (*ovo_mat.emissive, 1.0)

        # Optionally load texture files from self.texture_directory.
        # (Texture handling code can be added here.)

        return mat

    # --------------------------------------------------
    #  Apply Physics
    # --------------------------------------------------
    def _apply_physics(self, obj, phys):
        """
        Applies physics settings to a mesh object using Blender's rigid body system.

        :param obj: The Blender mesh object.
        :param phys: An OVOPhysicsData instance containing physics parameters.
        """
        # Ensure a rigid body world exists in the scene.
        if not bpy.context.scene.rigidbody_world:
            bpy.ops.rigidbody.world_add()

        # Set the object as active and select it.
        bpy.context.view_layer.objects.active = obj
        obj.select_set(True)

        bpy.ops.rigidbody.object_add(type='ACTIVE')

        rb = obj.rigid_body

        # Set the type based on the physics data.
        if phys.obj_type == 1:
            rb.type = 'ACTIVE'
        elif phys.obj_type == 3:
            rb.type = 'PASSIVE'
        else:
            rb.type = 'ACTIVE'

        HULL_MAP = {
            HullType.HULL_SPHERE: "SPHERE",
            HullType.HULL_BOX: "BOX",
            HullType.HULL_CAPSULE: "CAPSULE",
            HullType.HULL_CONVEX: "CONVEX_HULL",
        }

        def get_blender_collision_shape(hull_type: int) -> str:
            # Default to 'BOX' if hull_type is not recognized
            return HULL_MAP.get(hull_type, "BOX")

        # Set additional physics properties.
        rb.collision_shape = get_blender_collision_shape(phys.hull_type)
        rb.mass = phys.mass
        rb.friction = phys.dyn_fric
        rb.restitution = phys.bounciness
        rb.linear_damping = phys.lin_damp
        rb.angular_damping = phys.ang_damp

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
        For each NodeRecord:
          - Converts the raw_matrix (a list of tuples, row-major) to a mathutils.Matrix.
          - Transposes it to obtain Blender's column-major matrix.
          - If the object is parented to a "[root]" object, an extra rotation may be applied.
          - For LIGHT nodes, a quaternion correction is applied based on the light’s parsed direction.
            (This replicates the old importer behavior.)
          - For all other node types, the matrix is applied as is.
        """

        # A simple local logger (you may later move this to your utils module).
        def log_info(message, indent=0):
            prefix = "  " * indent
            print(f"{prefix}{message}")

        log_info("[OVOImporter] Applying transformations.")

        for rec in self.node_records:
            # Skip the fake root node.
            if rec.name == "[root]":
                log_info("Skipping [root] node.", indent=1)
                continue

            # Retrieve the Blender object from the mapping.
            obj = self.record_to_object.get(rec)
            if not obj:
                log_info(f"Node '{rec.name}' has no associated Blender object. Skipping.", indent=1)
                continue

            # Convert the raw matrix (list of 4-tuples) to a mathutils.Matrix and transpose.
            mat = mathutils.Matrix(rec.raw_matrix)
            mat.transpose()  # now mat is in Blender's column-major format

            # (Optional) Apply an extra +90° rotation for nodes parented to [root]
            # Uncomment or adjust as needed for your scene.
            if obj.parent and obj.parent.name == "[root]":
                conv_90_x = mathutils.Matrix([
                    [1, 0, 0, 0],
                    [0, 0, -1, 0],
                    [0, 1, 0, 0],
                    [0, 0, 0, 1]
                ])
                mat = conv_90_x @ mat
                log_info(f"Extra +90° X rotation applied to '{rec.name}' because parent is [root].", indent=1)

            # Special handling for light nodes:
            if rec.node_type == "LIGHT":
                # If the light type is DIRECTIONAL (or if you want to apply this to all lights),
                # ensure that the light quaternion is computed.
                if rec.light_type == LightType.DIRECTIONAL:
                    # If not already set, compute it using the old logic.
                    if rec.light_quat is None:
                        # Use (0, 0, -1) as the default light direction.
                        default_dir = mathutils.Vector((0, 0, -1))
                        # rec.direction is expected to be a 3-tuple from the file.
                        target_dir = mathutils.Vector(rec.direction).normalized()
                        rec.light_quat = default_dir.rotation_difference(target_dir)
                        log_info(f"Computed light_quat for '{rec.name}' from direction {rec.direction}.", indent=2)
                # If a quaternion correction exists, apply it.
                if rec.light_quat:
                    # Decompose the matrix into location, rotation, and scale.
                    loc, base_rot, scale = mat.decompose()
                    log_info(f"Light '{rec.name}' decomposition:", indent=1)
                    log_info(f"  Location = {loc}", indent=2)
                    log_info(f"  Base rotation (Euler) = {base_rot.to_euler('XYZ')}", indent=2)
                    log_info(f"  Scale = {scale}", indent=2)

                    # Compute the corrected rotation by multiplying the light quaternion (from file)
                    # on the left of the base rotation, as in the old implementation.
                    corrected_rot = rec.light_quat @ base_rot
                    log_info(f"Corrected rotation (Euler) = {corrected_rot.to_euler('XYZ')}", indent=2)

                    # Reconstruct the final transformation matrix.
                    final_mat = corrected_rot.to_matrix().to_4x4()
                    # Reapply scale.
                    final_mat[0][0] *= scale.x
                    final_mat[1][1] *= scale.y
                    final_mat[2][2] *= scale.z
                    # Set the translation.
                    final_mat[0][3] = loc.x
                    final_mat[1][3] = loc.y
                    final_mat[2][3] = loc.z

                    obj.matrix_basis = final_mat
                    log_info(f"Final transformation for light '{rec.name}' applied: {final_mat.to_euler('XYZ')}",
                             indent=1)
                    continue  # skip applying the non-light matrix below

            # For non-light nodes, apply the computed matrix.
            obj.matrix_basis = mat
