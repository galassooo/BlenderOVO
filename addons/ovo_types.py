# ================================================================
# OVO TYPES
# ================================================================
# Defines constants, enumerations, and default values used across
# the OVO Blender plugin for import/export functionality.
#
# Centralizes shared types to avoid duplication and ensure
# consistent maintenance of the codebase.
# ================================================================


# --------------------------------------------------------
# Chunk Type Enumeration
# --------------------------------------------------------
class ChunkType:
    """
    Enumeration of chunk types within an OVO file.
    Each chunk represents a different type of data.
    """
    OBJECT = 0         # Object Chunk
    NODE = 1           # Generic node
    OBJECT2D = 2       # 2D object
    OBJECT3D = 3       # 3D object
    LIST = 4           # Data list
    BUFFER = 5         # Data buffer
    SHADER = 6         # Shader data
    TEXTURE = 7        # Texture
    FILTER = 8         # Filter
    MATERIAL = 9       # Material
    FBO = 10           # Framebuffer Object
    QUAD = 11          # Quad
    BOX = 12           # Box
    SKYBOX = 13        # Skybox
    FONT = 14          # Font
    CAMERA = 15        # Camera
    LIGHT = 16         # Light
    BONE = 17          # Bone
    MESH = 18          # Mesh
    SKINNED = 19       # Skinned Mesh
    INSTANCED = 20     # Instanced Object
    PIPELINE = 21      # Rendering Pipeline
    EMITTER = 22       # Particle Emitter
    ANIM = 23          # Animation
    PHYSICS = 24       # Physics Data
    LAST = 25          # Marker for last chunk type

# --------------------------------------------------------
# Collision Hull Types (Physics)
# --------------------------------------------------------
class HullType:
    """
    Enumeration of collision hull types used for physics.
    Describes the shape used for collision detection.
    """
    HULL_UNDEFINED = 0      # Undefined
    HULL_SPHERE = 1         # Sphere
    HULL_BOX = 2            # Box
    HULL_CAPSULE = 3        # Capsule
    HULL_CONVEX = 4         # Convex hull
    HULL_ORIGINAL = 5       # Original mesh shape
    HULL_CUSTOM = 6         # Custom shape
    HULL_CONCAVE = 7        # Concave mesh
    HULL_LAST = 8           # End-of-range marker

# --------------------------------------------------------
# Light Types
# --------------------------------------------------------
class LightType:
    """
    Enumeration of supported light types in the OVO format.
    """
    OMNI = 0          # Point light
    DIRECTIONAL = 1   # Directional light
    SPOT = 2          # Spot light

# --------------------------------------------------------
# Physics Object Types
# --------------------------------------------------------
class PhysicsType:
    """
    Enumeration of physics object behaviors.
    """
    STATIC = 0        # Static object (non-movable)
    DYNAMIC = 1       # Dynamic object (affected by forces)

# --------------------------------------------------------
# Texture Compression Formats
# --------------------------------------------------------
class TextureFormat:
    """
    Supported texture compression formats.
    Includes mapping for use with Compressonator tools.
    """
    # Legacy S3TC formats
    DXT1 = "dxt1"  # No alpha or binary alpha
    DXT5 = "dxt5"  # With alpha channel

    # High-quality BPTC formats
    BC5 = "bc5"  # Ideal for normal maps (2-channel)
    BC7 = "bc7"  # High-quality with alpha support

    # Format mapping for Compressonator
    FORMAT_MAP = {
        DXT1: "BC1",
        DXT5: "BC3",
        BC5: "BC5",
        BC7: "BC7"
    }

# --------------------------------------------------------
# General OVO Format Constants
# --------------------------------------------------------
OVO_VERSION = 8                 # Current OVO format version
NONE_PLACEHOLDER = "[none]"     # Placeholder for null values
ROOT_NODE_NAME = "[root]"       # Name used for root node

# --------------------------------------------------------
# Default Material Values
# --------------------------------------------------------
DEFAULT_BASE_COLOR = (0.8, 0.8, 0.8)  # Default base color
DEFAULT_EMISSION = (0.0, 0.0, 0.0)    # Default emission color
DEFAULT_ROUGHNESS = 0.5              # Default roughness
DEFAULT_METALLIC = 0.0               # Default metallic value
DEFAULT_ALPHA = 1.0                  # Default alpha

# --------------------------------------------------------
# Coordinate Conversion Constants
# --------------------------------------------------------
BLENDER_TO_OVO_ROTATION = (-90.0, 'X')  # Rotation to convert Blender to OVO space

# --------------------------------------------------------
# Physics Defaults
# --------------------------------------------------------
DEFAULT_MASS = 1.0              # Default mass
DEFAULT_FRICTION = 0.5          # Default friction
DEFAULT_RESTITUTION = 0.0       # Default restitution (bounciness)
DEFAULT_LINEAR_DAMPING = 0.04   # Default linear damping
DEFAULT_ANGULAR_DAMPING = 0.1   # Default angular damping

# --------------------------------------------------------
# Light Defaults
# --------------------------------------------------------
MAX_SPOT_ANGLE = 40.0           # Maximum spot light angle (degrees)
DEFAULT_POINT_ANGLE = 180.0     # Default point light angle (for visual debug)
DEFAULT_DIRECTIONAL_ANGLE = 0.0 # Default angle for directional lights

# --------------------------------------------------------
# ANSI Color Codes for Logging
# --------------------------------------------------------
GREEN = '\033[92m'     # Color for mesh elements
YELLOW = '\033[93m'    # Color for lights
BLUE = '\033[94m'      # Color for generic nodes
RED = '\033[91m'       # Color for warnings/errors
MAGENTA = '\033[95m'   # Color for materials
RESET = '\033[0m'      # Reset ANSI color
BOLD = '\033[1m'       # Bold text