import bpy
import os
import traceback
from bpy_extras.io_utils import ExportHelper
from bpy.props import StringProperty, BoolProperty, EnumProperty
from bpy.types import Operator, Panel

# Importa il core dell'esportatore
try:
    # Per quando eseguito come addon
    from .ovo_exporter_core import OVO_Exporter
except ImportError:
    # Per quando eseguito direttamente
    from ovo_exporter_core import OVO_Exporter


class OVO_PT_export_main(Operator, ExportHelper):
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

    # Aggiunto nuovo parametro per il flip delle texture
    flip_textures: BoolProperty(
        name="Flip Textures Vertically",
        description="Flip textures vertically during export (recommended for most engines)",
        default=True,
    )

    def draw(self, context):
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
        try:
            exporter = OVO_Exporter(
                context,
                self.filepath,
                use_mesh=self.use_mesh,
                use_light=self.use_light,
                use_legacy_compression=self.use_legacy_compression,
                flip_textures=self.flip_textures  # Passa il nuovo parametro all'esportatore
            )

            # Esegui l'export
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
    # define export menu item
    self.layout.operator(OVO_PT_export_main.bl_idname, text="OverView Object (.ovo)")


def register():
    try:
        bpy.utils.unregister_class(OVO_PT_export_main)
        print("Operator già registrato, deregistrato prima di una nuova registrazione.")
    except RuntimeError:
        print("Operator non era registrato, procedo normalmente.")

    bpy.utils.register_class(OVO_PT_export_main)
    bpy.types.TOPBAR_MT_file_export.append(menu_func_export)


def unregister():
    try:
        bpy.utils.unregister_class(OVO_PT_export_main)
        bpy.types.TOPBAR_MT_file_export.remove(menu_func_export)
    except RuntimeError:
        print("Operator non era registrato, skipping unregister.")