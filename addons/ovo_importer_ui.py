# ================================================================
# IMPORTER UI MODULE
# ================================================================
# This module defines the Blender Operator (OT_ImportOVO)
# responsible for importing an OVO file into Blender.
# It also adds the operator to the File > Import menu.
# ================================================================

# --------------------------------------------------------
# IMPORTS
# --------------------------------------------------------
import bpy
from bpy_extras.io_utils import ImportHelper
from bpy.props import StringProperty, BoolProperty
from bpy.types import Operator

try:
    from .ovo_importer_core import OVOImporter
    from .ovo_material_factory import MaterialFactory
    from .ovo_log import log
except ImportError:
    from ovo_importer_core import OVOImporter
    from ovo_material_factory import MaterialFactory
    from ovo_log import log

# --------------------------------------------------------
# OT_IMPORTOVO
# --------------------------------------------------------
class OT_ImportOVO(Operator, ImportHelper):
    """Operator to import an OVO file into Blender."""
    bl_idname = "import_scene.ovo"
    bl_label = "Import OVO"

    filename_ext = ".ovo"
    filter_glob: StringProperty(default="*.ovo", options={'HIDDEN'})

    flip_textures: BoolProperty(
        name="Flip Textures",
        description="Flip textures vertically during import",
        default=True
    )

    def execute(self, context):
        """
        Execute the import:
          - Instantiate OVOImporter with the chosen filepath.
          - Call import_scene() and return FINISHED or CANCELLED.
        """
        importer = OVOImporter(self.filepath)

        importer.flip_textures = self.flip_textures

        result = importer.import_scene()

        bpy.context.view_layer.update()
        return result

def menu_func_import_importer(self, context):
    """Add the import option to the File > Import menu."""
    self.layout.operator(OT_ImportOVO.bl_idname, text="OverVision Object (.ovo)")

# --------------------------------------------------------
# REGISTER / UNREGISTER IMPORTER
# --------------------------------------------------------
def register():
    """Register the importer operator and menu entry."""
    try:
        bpy.utils.unregister_class(OT_ImportOVO)
        log("Operator was already registered; unregistering first.", category="")
    except RuntimeError:
        log("Operator not registered; proceeding normally.", category="")

    bpy.utils.register_class(OT_ImportOVO)
    bpy.types.TOPBAR_MT_file_import.append(menu_func_import_importer)

    log("OVO Importer registered successfully.", category="")


def unregister():
    """Unregister the importer operator and remove menu entry."""
    try:
        bpy.utils.unregister_class(OT_ImportOVO)
        bpy.types.TOPBAR_MT_file_import.remove(menu_func_import_importer)
        log("OVO Importer unregistered successfully.", category="")
    except RuntimeError:
        log("Operator not registered; skipping unregister.", category="")