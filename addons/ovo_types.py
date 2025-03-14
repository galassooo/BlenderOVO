"""
Modulo ovo_types.py
Definisce le costanti e le enumerazioni utilizzate nel formato OVO.

Questo modulo centralizza tutte le definizioni di tipi e costanti per
evitare duplicazioni e migliorare la manutenibilità del codice.
"""


class ChunkType:
    """
    Enumerazione dei tipi di chunk nel formato OVO.
    Ogni chunk rappresenta un diverso tipo di dato nel file.
    """
    OBJECT = 0  # Chunk principale (versione)
    NODE = 1  # Nodo generico
    OBJECT2D = 2  # Oggetto 2D
    OBJECT3D = 3  # Oggetto 3D
    LIST = 4  # Lista
    BUFFER = 5  # Buffer
    SHADER = 6  # Shader
    TEXTURE = 7  # Texture
    FILTER = 8  # Filtro
    MATERIAL = 9  # Materiale
    FBO = 10  # Framebuffer Object
    QUAD = 11  # Quad
    BOX = 12  # Box
    SKYBOX = 13  # Skybox
    FONT = 14  # Font
    CAMERA = 15  # Camera
    LIGHT = 16  # Luce
    BONE = 17  # Osso (per animazioni)
    MESH = 18  # Mesh
    SKINNED = 19  # Mesh skinnata
    INSTANCED = 20  # Istanza
    PIPELINE = 21  # Pipeline
    EMITTER = 22  # Emettitore di particelle
    ANIM = 23  # Animazione
    PHYSICS = 24  # Fisica
    LAST = 25  # Ultimo (per controllo range)


class HullType:
    """
    Enumerazione dei tipi di hull collision per la fisica.
    Definisce le forme di collisione disponibili per gli oggetti fisici.
    """
    HULL_UNDEFINED = 0  # Non definito
    HULL_SPHERE = 1  # Sfera
    HULL_BOX = 2  # Box
    HULL_CAPSULE = 3  # Capsula
    HULL_CONVEX = 4  # Convex hull
    HULL_ORIGINAL = 5  # Forma originale
    HULL_CUSTOM = 6  # Personalizzato
    HULL_CONCAVE = 7  # Concave mesh
    HULL_LAST = 8  # Ultimo (per controllo range)


class LightType:
    """
    Enumerazione dei tipi di luce.
    """
    OMNI = 0  # Luce puntiforme (point light)
    DIRECTIONAL = 1  # Luce direzionale (directional light)
    SPOT = 2  # Luce spot (spotlight)


class PhysicsType:
    """
    Enumerazione dei tipi di fisica.
    """
    STATIC = 0  # Oggetto statico
    DYNAMIC = 1  # Oggetto dinamico


class TextureFormat:
    """
    Formati di compressione delle texture.
    """
    # Formati S3TC (legacy)
    DXT1 = "dxt1"  # Compressione senza alpha o alpha binario
    DXT5 = "dxt5"  # Compressione con canale alpha

    # Formati BPTC (migliore qualità)
    BC5 = "bc5"  # Per normal maps (2 canali)
    BC7 = "bc7"  # Per texture con alpha (alta qualità)

    # Mappatura ai formati Compressonator
    FORMAT_MAP = {
        DXT1: "BC1",
        DXT5: "BC3",
        BC5: "BC5",
        BC7: "BC7"
    }


# Costanti per la versione OVO
OVO_VERSION = 8  # Versione corrente del formato OVO

# Costanti per placeholder
NONE_PLACEHOLDER = "[none]"  # Placeholder per valori nulli
ROOT_NODE_NAME = "[root]"  # Nome del nodo root

# Costanti per valori di default dei materiali
DEFAULT_BASE_COLOR = (0.8, 0.8, 0.8)  # Colore base di default
DEFAULT_EMISSION = (0.0, 0.0, 0.0)  # Emissione di default
DEFAULT_ROUGHNESS = 0.5  # Rugosità di default
DEFAULT_METALLIC = 0.0  # Metallicità di default
DEFAULT_ALPHA = 1.0  # Alpha di default

# Costanti per conversione coordinate
BLENDER_TO_OVO_ROTATION = (-90.0, 'X')  # Rotazione per convertire da Blender a OVO

# Costanti per la fisica
DEFAULT_MASS = 1.0  # Massa di default
DEFAULT_FRICTION = 0.5  # Attrito di default
DEFAULT_RESTITUTION = 0.0  # Rimbalzo di default
DEFAULT_LINEAR_DAMPING = 0.04  # Smorzamento lineare di default
DEFAULT_ANGULAR_DAMPING = 0.1  # Smorzamento angolare di default

# Costanti per luci
MAX_SPOT_ANGLE = 40.0  # Angolo massimo per spot light
DEFAULT_POINT_ANGLE = 180.0  # Angolo di default per point light
DEFAULT_DIRECTIONAL_ANGLE = 0.0  # Angolo di default per directional light

#costanti per colori
# ANSI color codes
GREEN = '\033[92m'  # For mesh objects
YELLOW = '\033[93m'  # For light objects
BLUE = '\033[94m'  # For regular nodes
RED = '\033[91m'  # For warning/important info
RESET = '\033[0m'  # Reset color
BOLD = '\033[1m'  # Bold text