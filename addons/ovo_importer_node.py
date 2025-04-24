# ================================================================
#  OVO IMPORTER NODES & MATERIALS
# ================================================================
# This module defines the core data structures used by the importer
# to represent data extracted from the .ovo file.
#
# Classes included:
#   - OVOMaterial: Container for material data (colors, textures, etc.).
#   - OVOPhysicsData: Container for physics parameters (mass, friction, etc.).
#   - NodeRecord: A unified container to hold information about a node.
#                It can represent a generic node, a mesh, or a light.
#
# These classes hold only the data parsed from the file and do not interact
# directly with Blender's API; they are later used by the scene builder to
# create actual Blender objects.
# ================================================================

# --------------------------------------------------------
# OVOMaterial
# --------------------------------------------------------
class OVOMaterial:
    """
    Basic container for material data.

    Attributes:
        name (str): The material name.
        base_color (tuple): A 3-tuple (r, g, b) representing the base color.
        roughness (float): Roughness value.
        metallic (float): Metallic value.
        transparency (float): Transparency (alpha) value.
        emissive (tuple): A 3-tuple (ex, ey, ez) representing emissive color.
        textures (dict): Dictionary containing texture file names keyed by type (e.g., "albedo", "normal", etc.).
    """

    def __init__(self, name, base_color, roughness, metallic, transparency, emissive, textures):
        self.name = name
        self.base_color = base_color
        self.roughness = roughness
        self.metallic = metallic
        self.transparency = transparency
        self.emissive = emissive
        self.textures = textures
        self.blender_material = None

# --------------------------------------------------------
# OVOPhysicsData
# --------------------------------------------------------
class OVOPhysicsData:
    """
    Container for physics parameters parsed from a mesh chunk.

    Attributes:
        obj_type (int): Indicates dynamic or static physics.
        hull_type (int): The collision hull type.
        mass (float): Mass of the object.
        static_fric (float): Static friction coefficient.
        dyn_fric (float): Dynamic friction coefficient.
        bounciness (float): How bouncy the object is.
        lin_damp (float): Linear damping coefficient.
        ang_damp (float): Angular damping coefficient.
    """

    def __init__(self, obj_type, hull_type, mass, static_fric, dyn_fric, bounciness, lin_damp, ang_damp):
        self.obj_type = obj_type
        self.hull_type = hull_type
        self.mass = mass
        self.static_fric = static_fric
        self.dyn_fric = dyn_fric
        self.bounciness = bounciness
        self.lin_damp = lin_damp
        self.ang_damp = ang_damp

# --------------------------------------------------------
# NodeRecord
# --------------------------------------------------------
class NodeRecord:
    """
    Unified container for node data extracted from the .ovo file.

    This class is used to represent:
      - Generic nodes (node_type="NODE")
      - Meshes (node_type="MESH")
      - Lights (node_type="LIGHT")

    Attributes:
        name (str): Name of the node.
        node_type (str): "NODE", "MESH", or "LIGHT".
        children_count (int): The number of children nodes expected.
        raw_matrix (list): A 4x4 list (row-major) representing the node's transform.
        blender_object: A placeholder for the Blender object created later.
        parent: Reference to the parent NodeRecord (if any).

    Additional attributes for MESH:
        material_name (str): Name of the material to apply.
        vertices (list): List of vertex positions (tuples).
        faces (list): List of faces (each a tuple of vertex indices).
        uvs (list): List of UV coordinates (tuples).
        physics_data (OVOPhysicsData): Container for physics-related data.
        lod_count (int): The number of Levels Of Detail.

    Additional attributes for LIGHT:
        light_type (int): Numeric code representing the light type.
        color (tuple): RGB color of the light.
        radius (float): Influences light energy.
        direction (tuple): Direction vector of the light.
        cutoff (float): Cutoff angle.
        spot_exponent (float): Spot falloff.
        shadow (int): Shadow flag.
        volumetric (int): Volumetric flag.
    """

    def __init__(self, name, node_type, children_count, raw_matrix):
        self.name = name
        self.node_type = node_type
        self.children_count = children_count
        self.raw_matrix = raw_matrix

        # Hierarchy / reference placeholders
        self.blender_object = None
        self.parent = None

        # Mesh-specific
        self.material_name = None
        self.vertices = []
        self.faces = []
        self.uvs = []
        self.physics_data = None
        self.lod_count = 0

        # Light-specific
        self.light_type = None
        self.color = None
        self.radius = 0.0
        self.direction = None
        self.cutoff = 0.0
        self.spot_exponent = 0.0
        self.shadow = 0
        self.volumetric = 0
        self.light_quat = None

        # Bounding box data
        self.bounding_radius = 0.0
        self.min_box = (0.0, 0.0, 0.0)
        self.max_box = (0.0, 0.0, 0.0)

    def __repr__(self):
        return f"NodeRecord(name={self.name}, type={self.node_type}, children_count={self.children_count})"