# ================================================================
# EXPORTER UI MODULE
# ================================================================
# This module defines the Blender Operator (OVO_PT_export_main)
# responsible for exporting the current scene to an OVO file.
# It also adds the operator to the File > Export menu.
# ================================================================

# --------------------------------------------------------
# IMPORTS
# --------------------------------------------------------
import bpy
from bpy_extras.io_utils import ExportHelper
from bpy.props import StringProperty, BoolProperty, EnumProperty
from bpy.types import Operator, Panel

try:
    from .ovo_exporter_core import OVO_Exporter
    from .ovo_log import log
except ImportError:
    from ovo_exporter_core import OVO_Exporter
    from ovo_log import log

# --------------------------------------------------------
# OT_ExportOVO
# --------------------------------------------------------
class OT_ExportOVO(Operator, ExportHelper):
    """Operator to export the current scene to an OVO file."""
    bl_idname = "export_scene.ovo"
    bl_label = "Export OVO"

    filename_ext = ".ovo"
    filter_glob: StringProperty(
        default="*.ovo",
        options={'HIDDEN'},
    )

    use_mesh: BoolProperty(
        name="Include Meshes",
        description="Include mesh objects in the export",
        default=True,
    )

    use_light: BoolProperty(
        name="Include Lights",
        description="Include light objects in the export",
        default=True,
    )

    # Modified compression format to be a simple toggle
    use_legacy_compression: BoolProperty(
        name="Use S3TC Compression",
        description="Use legacy S3TC compression (DXT1/DXT5) instead of higher quality BPTC compression (BC7)",
        default=True,
    )

    flip_textures: BoolProperty(
        name="Flip Textures Vertically",
        description="Flip textures vertically during export (recommended for most engines)",
        default=True,
    )

    def draw(self, context):
        """Layout for export options."""
        layout = self.layout

        # Include/Exclude Objects
        box = layout.box()
        box.label(text="Include:", icon='GHOST_ENABLED')
        row = box.row()
        row.prop(self, "use_mesh")
        row.prop(self, "use_light")

        # Texture Settings
        box = layout.box()
        box.label(text="Texture Settings:", icon='TEXTURE')
        box.prop(self, "use_legacy_compression")
        box.prop(self, "flip_textures")

    def execute(self, context):
        """
       Execute the export:
         - Instantiate OVO_Exporter with current options.
         - Run export() and return FINISHED or CANCELLED.
       """
        try:
            exporter = OVO_Exporter(
                context,
                self.filepath,
                use_mesh=self.use_mesh,
                use_light=self.use_light,
                use_legacy_compression=self.use_legacy_compression,
                flip_textures=self.flip_textures
            )

            if exporter.export():
                self.report({'INFO'}, "Export completed successfully")
                return {'FINISHED'}
            else:
                self.report({'ERROR'}, "Export failed. Check system console for details.")
                return {'CANCELLED'}

        except Exception as e:
            import traceback
            self.report({'ERROR'}, f"Export failed: {str(e)}")
            return {'CANCELLED'}


def menu_func_export(self, context):
    """Add the export option to the File > Export menu."""
    self.layout.operator(OT_ExportOVO.bl_idname, text="OverView Object (.ovo)")

# --------------------------------------------------------
# REGISTER / UNREGISTER EXPORTER
# --------------------------------------------------------
def register():
    """Register the exporter operator and menu entry."""
    try:
        bpy.utils.unregister_class(OT_ExportOVO)
        log("Operator was already registered; unregistering first.", category="")
    except RuntimeError:
        log("Operator not registered; proceeding normally.", category="")

    bpy.utils.register_class(OT_ExportOVO)
    bpy.types.TOPBAR_MT_file_export.append(menu_func_export)
    log("OVO Exporter registered successfully.", category="")


def unregister():
    """Unregister the exporter operator and remove menu entry."""
    try:
        bpy.utils.unregister_class(OT_ExportOVO)
        bpy.types.TOPBAR_MT_file_export.remove(menu_func_export)
        log("OVO Exporter unregistered successfully.", category="")
    except RuntimeError:
        log("Operator not registered; skipping unregister.", category="")