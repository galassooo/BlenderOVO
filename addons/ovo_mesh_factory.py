# ================================================================
#  MESH FACTORY
# ================================================================
# This module defines the MeshFactory class, responsible for creating
# Blender Mesh objects from parsed mesh data (NodeRecord) including geometry,
# UV mapping, material assignment, and physics properties.
# ================================================================

# --------------------------------------------------------
# IMPORTS
# --------------------------------------------------------
import bpy
import mathutils

try:
    from .ovo_material_factory import MaterialFactory
    from .ovo_types import HullType
    from .ovo_log import log
except ImportError:
    from ovo_material_factory import MaterialFactory
    from ovo_types import HullType
    from ovo_log import log

# --------------------------------------------------------
# Mesh Factory
# --------------------------------------------------------
class MeshFactory:
    """
    MeshFactory creates a Blender Mesh object from mesh data provided in a NodeRecord.

    It handles the creation of mesh geometry from vertices and faces, sets up a UV map,
    assigns materials via the MaterialFactory, and configures physics properties if needed.
    """

    @staticmethod
    def create(rec, materials, texture_directory, flip_textures=True):
        """
        Creates a Blender mesh object from a parsed NodeRecord.

        Args:
            rec (NodeRecord): Parsed mesh data.
            materials (dict): Dictionary of OVOMaterial instances by name.
            texture_directory (str): Directory where textures are stored.
            flip_textures (bool): Whether to flip DDS textures vertically.

        Returns:
            bpy.types.Object: The newly created Blender mesh object.
        """
        # Create mesh data.
        if not rec.vertices:
            mesh_data = bpy.data.meshes.new(rec.name)
        else:
            mesh_data = bpy.data.meshes.new(rec.name)

            transformed_vertices = []
            for vertex in rec.vertices:
                transformed_vertex = MeshFactory.transform_vertex(vertex)
                transformed_vertices.append(transformed_vertex)

            mesh_data.from_pydata(transformed_vertices, [], rec.faces)
            mesh_data.update()
            # Create UV map if available.
            if rec.uvs and len(rec.uvs) == len(rec.vertices):
                uv_layer = mesh_data.uv_layers.new(name="UVMap")
                for poly in mesh_data.polygons:
                    for loop_idx in range(poly.loop_start, poly.loop_start + poly.loop_total):
                        vert_idx = mesh_data.loops[loop_idx].vertex_index
                        uv_layer.data[loop_idx].uv = rec.uvs[vert_idx]

        mesh_obj = bpy.data.objects.new(rec.name, mesh_data)
        if not mesh_obj.users_collection:
            bpy.context.collection.objects.link(mesh_obj)

            # Store bounding box data as custom properties if available
        if hasattr(rec, 'bounding_radius') and hasattr(rec, 'min_box') and hasattr(rec, 'max_box'):
            mesh_obj["ovo_bounding_radius"] = rec.bounding_radius
            mesh_obj["ovo_min_box"] = rec.min_box
            mesh_obj["ovo_max_box"] = rec.max_box

            # Log the bounding box information
            log(f"Bounding data: Radius={rec.bounding_radius}, Min={rec.min_box}, Max={rec.max_box}", category="MESH",
                indent=2)

        # Assign material if available.
        if rec.material_name and rec.material_name in materials:
            ovo_mat = materials[rec.material_name]
            mat = MaterialFactory.create(ovo_mat, texture_directory, flip_textures=flip_textures)
            if not mesh_obj.data.materials:
                mesh_obj.data.materials.append(mat)
            else:
                mesh_obj.data.materials[0] = mat

        # Apply physics if physics data is available.
        if hasattr(rec, 'physics_data') and rec.physics_data:
            MeshFactory.apply_physics(mesh_obj, rec.physics_data)

        log(f"Created mesh: '{rec.name}' | Vertices={len(rec.vertices)} Faces={len(rec.faces)} Material={rec.material_name}",category="MESH", indent=1)
        return mesh_obj

    # --------------------------------------------------------
    # Apply Physics
    # --------------------------------------------------------
    @staticmethod
    def apply_physics(obj, phys):
        """
        Applies physics properties from NodeRecord physics data to the Blender object.

        Args:
            obj (bpy.types.Object): The mesh object.
            phys (OVOPhysicsData): Physics configuration.
        """
        # Ensure a rigid body world exists.
        if not bpy.context.scene.rigidbody_world:
            bpy.ops.rigidbody.world_add()
        bpy.context.view_layer.objects.active = obj
        obj.select_set(True)
        bpy.ops.rigidbody.object_add(type='ACTIVE')
        rb = obj.rigid_body

        if phys.obj_type == 1:
            rb.type = 'ACTIVE'
        elif phys.obj_type == 3:
            rb.type = 'PASSIVE'
        else:
            rb.type = 'ACTIVE'

        # Collision shape mapping
        HULL_MAP = {
            HullType.HULL_SPHERE: "SPHERE",
            HullType.HULL_BOX: "BOX",
            HullType.HULL_CAPSULE: "CAPSULE",
            HullType.HULL_CONVEX: "CONVEX_HULL",
        }

        def get_blender_collision_shape(hull_type: int) -> str:
            # Default to 'BOX' if hull_type is not recognized
            return HULL_MAP.get(hull_type, "BOX")

        # Apply physics properties
        rb.collision_shape = get_blender_collision_shape(phys.hull_type)
        rb.friction = phys.dyn_fric
        rb.restitution = phys.bounciness
        rb.linear_damping = phys.lin_damp
        rb.angular_damping = phys.ang_damp
        obj.select_set(False)

        log(f"Applied physics to '{obj.name}' | Type={rb.type} Shape={rb.collision_shape}", category="MESH", indent=2)

    @staticmethod
    def transform_vertex(vertex):
        """
        Transform a vertex from OpenGL system to Blender system.

        Args:
            vertex (tuple): Original vertex coordinates (x, y, z)

        Returns:
            tuple: Transformed vertex coordinates
        """
        # Conversion matrix
        C = mathutils.Matrix((
            (1, 0, 0, 0),
            (0, 0, 1, 0),
            (0, -1, 0, 0),
            (0, 0, 0, 1)
        ))
        C_inv = C.transposed()

        # Convert the vertex in homogeneous coordinates
        v = mathutils.Vector((vertex[0], vertex[1], vertex[2], 1.0))
        transformed = C_inv @ v

        # Return the tuple without the homogeneous component
        return (transformed[0], transformed[1], transformed[2])