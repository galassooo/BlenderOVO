"""
Modulo ovo_types.py
Definisce le costanti e le enumerazioni utilizzate nel formato OVO.

Questo modulo centralizza tutte le definizioni di tipi, costanti e valori di default
per evitare duplicazioni e facilitare la manutenzione del codice.
"""

# --------------------------------------------------------
# Enumerazione per i Tipi di Chunk
# --------------------------------------------------------
class ChunkType:
    """
    Enumerazione dei tipi di chunk nel file OVO.
    Ogni chunk rappresenta un diverso tipo di dato.
    """
    OBJECT = 0         # Chunk principale: la versione del file OVO
    NODE = 1           # Nodo generico
    OBJECT2D = 2       # Oggetto 2D
    OBJECT3D = 3       # Oggetto 3D
    LIST = 4           # Lista di dati
    BUFFER = 5         # Buffer di dati
    SHADER = 6         # Dati del shader
    TEXTURE = 7        # Texture
    FILTER = 8         # Filtro
    MATERIAL = 9       # Materiale
    FBO = 10           # Framebuffer Object
    QUAD = 11          # Quad
    BOX = 12           # Box
    SKYBOX = 13        # Skybox
    FONT = 14          # Font
    CAMERA = 15        # Camera
    LIGHT = 16         # Luce
    BONE = 17          # Osso (per animazioni)
    MESH = 18          # Mesh (geometria)
    SKINNED = 19       # Mesh skinnata
    INSTANCED = 20     # Istanza di oggetto
    PIPELINE = 21      # Pipeline grafica
    EMITTER = 22       # Emettitore di particelle
    ANIM = 23          # Animazione
    PHYSICS = 24       # Dati di fisica
    LAST = 25          # Marker per ultimo tipo (usato per controllo)

# --------------------------------------------------------
# Enumerazione per i Tipi di Collision Hull (Fisica)
# --------------------------------------------------------
class HullType:
    """
    Enumerazione dei tipi di hull collision usati per la fisica.
    Indica la forma di collisione utilizzata dall'oggetto.
    """
    HULL_UNDEFINED = 0   # Non definito
    HULL_SPHERE = 1      # Sfera
    HULL_BOX = 2         # Box
    HULL_CAPSULE = 3     # Capsula
    HULL_CONVEX = 4      # Convezione (convex hull)
    HULL_ORIGINAL = 5    # Forma originale
    HULL_CUSTOM = 6      # Formato personalizzato
    HULL_CONCAVE = 7     # Mesh concava
    HULL_LAST = 8        # Marker di fine (per controlli di range)

# --------------------------------------------------------
# Enumerazione per i Tipi di Luce
# --------------------------------------------------------
class LightType:
    """
    Enumerazione dei tipi di luce nel formato OVO.
    """
    OMNI = 0          # Luce puntiforme
    DIRECTIONAL = 1   # Luce direzionale
    SPOT = 2          # Luce spot

# --------------------------------------------------------
# Enumerazione per i Tipi di Fisica
# --------------------------------------------------------
class PhysicsType:
    """
    Enumerazione dei tipi di fisica per gli oggetti.
    """
    STATIC = 0        # Oggetto statico
    DYNAMIC = 1       # Oggetto dinamico

# --------------------------------------------------------
# Formati di Compressione delle Texture
# --------------------------------------------------------
class TextureFormat:
    """
    Definisce i formati di compressione delle texture supportati.
    Include anche una mappatura per converter via Compressonator.
    """
    # Formati S3TC (Legacy)
    DXT1 = "dxt1"     # Compressione S3TC senza canale alpha o con alpha binario
    DXT5 = "dxt5"     # Compressione S3TC con canale alpha

    # Formati BPTC (Alta Qualità)
    BC5 = "bc5"       # Adatto per normal maps (due canali)
    BC7 = "bc7"       # Alta qualità per texture con alpha

    # Mappatura dei formati per Compressonator
    FORMAT_MAP = {
        DXT1: "BC1",
        DXT5: "BC3",
        BC5: "BC5",
        BC7: "BC7"
    }

# --------------------------------------------------------
# Costanti Generali del Formato OVO
# --------------------------------------------------------
OVO_VERSION = 8              # Versione corrente del formato OVO
NONE_PLACEHOLDER = "[none]"    # Placeholder per valori nulli
ROOT_NODE_NAME = "[root]"      # Nome usato per il nodo radice fittizio

# --------------------------------------------------------
# Valori di Default per Materiali
# --------------------------------------------------------
DEFAULT_BASE_COLOR = (0.8, 0.8, 0.8)  # Colore base predefinito
DEFAULT_EMISSION = (0.0, 0.0, 0.0)      # Emissione di default
DEFAULT_ROUGHNESS = 0.5                 # Rugosità predefinita
DEFAULT_METALLIC = 0.0                  # Metallicità predefinita
DEFAULT_ALPHA = 1.0                     # Alpha predefinito

# --------------------------------------------------------
# Costanti per la Conversione delle Coordinate
# --------------------------------------------------------
BLENDER_TO_OVO_ROTATION = (-90.0, 'X')  # Rotazione per convertire da Blender a OVO

# --------------------------------------------------------
# Costanti per la Fisica
# --------------------------------------------------------
DEFAULT_MASS = 1.0              # Massa predefinita
DEFAULT_FRICTION = 0.5          # Attrito predefinito
DEFAULT_RESTITUTION = 0.0       # Rimbalzo predefinito
DEFAULT_LINEAR_DAMPING = 0.04   # Smorzamento lineare predefinito
DEFAULT_ANGULAR_DAMPING = 0.1     # Smorzamento angolare predefinito

# --------------------------------------------------------
# Costanti per le Luci
# --------------------------------------------------------
MAX_SPOT_ANGLE = 40.0           # Angolo massimo per spot
DEFAULT_POINT_ANGLE = 180.0     # Angolo di default per luce puntiforme
DEFAULT_DIRECTIONAL_ANGLE = 0.0  # Angolo di default per luce direzionale

# --------------------------------------------------------
# Costanti per i Colori (ANSI)
# --------------------------------------------------------
GREEN = '\033[92m'    # Colore per elementi del modello (mesh)
YELLOW = '\033[93m'   # Colore per le luci
BLUE = '\033[94m'     # Colore per nodi generici
RED = '\033[91m'      # Colore per messaggi di avviso
RESET = '\033[0m'     # Ripristino del colore
BOLD = '\033[1m'      # Testo in grassetto
