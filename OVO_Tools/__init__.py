"""
OVO Tools - Blender addon for importing and exporting OVO files.
"""

bl_info = {
    "name": "OVO Tools (Importer & Exporter)",
    "author": "Kevin Quarenghi & Martina Galasso",
    "version": (1, 0),
    "blender": (4, 2, 1),
    "location": "File > Import/Export > OverView Object (.ovo)",
    "description": "Import & Export the current scene to the OVO file format",
    "category": "Import-Export",
}

# --------------------------------------------------------
# IMPORTA I MODULI NECESSARI
# --------------------------------------------------------
import bpy
from bpy_extras.io_utils import ExportHelper
from bpy.props import StringProperty, BoolProperty, EnumProperty
from bpy.types import Operator, Panel

import sys
import os

# Ottieni il percorso assoluto della directory che contiene questo file
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.append(current_dir)

# --------------------------------------------------------
# IMPORTA I MODULI DELL'ADD-ON (EXPORTER SIDE)
# --------------------------------------------------------
from ovo_types import ChunkType, HullType
from ovo_packer import OVOPacker
from ovo_texture_manager import OVOTextureManager
from ovo_exporter_core import OVO_Exporter
from ovo_lod_manager import OVOLodManager
from ovo_exporter_ui import OVO_PT_export_main, menu_func_export, register, unregister

# --------------------------------------------------------
# IMPORTER IMPORTS
# --------------------------------------------------------
try:
    from .ovo_importer_ui import OT_ImportOVO, menu_func_import_importer
except ImportError:
    from ovo_importer_ui import OT_ImportOVO, menu_func_import_importer

# --------------------------------------------------------
# MENU FUNCTIONS
# --------------------------------------------------------
def menu_func_export(self, context):
    """Aggiunge la voce di menu per l'esportazione OVO"""
    self.layout.operator(OVO_PT_export_main.bl_idname, text="OverView Object (.ovo)")

# --------------------------------------------------------
# REGISTER / UNREGISTER
# --------------------------------------------------------
def register():
    """
    Registers all operators and menu functions for both
    the OVO exporter and importer within a single add-on.
    """
    # === Exporter Registration ===
    try:
        bpy.utils.unregister_class(OVO_PT_export_main)
        print("Operator già registrato, deregistrato prima di una nuova registrazione.")
    except RuntimeError:
        print("Operator non era registrato, procedo normalmente.")

    bpy.utils.register_class(OVO_PT_export_main)
    bpy.types.TOPBAR_MT_file_export.append(menu_func_export)
    print("OVO Exporter registrato con successo.")

    # === Importer Registration ===
    try:
        bpy.utils.unregister_class(OT_ImportOVO)
    except RuntimeError:
        print("Operator was not registered, proceed normally.")

    bpy.utils.register_class(OT_ImportOVO)
    bpy.types.TOPBAR_MT_file_import.append(menu_func_import_importer)
    print("OVO Importer registered successfully.")


def unregister():
    """
    Unregisters all operators and menu items for both
    the OVO exporter and importer.
    """
    # === Exporter Unregister ===
    try:
        bpy.utils.unregister_class(OVO_PT_export_main)
        bpy.types.TOPBAR_MT_file_export.remove(menu_func_export)
        print("OVO Exporter deregistrato con successo.")
    except RuntimeError:
        print("Operator non era registrato, skipping unregister.")

    # === Importer Unregister ===
    try:
        bpy.utils.unregister_class(OT_ImportOVO)
        bpy.types.TOPBAR_MT_file_import.remove(menu_func_import_importer)
        print("OVO Importer unregistered successfully.")
    except RuntimeError:
        print("OVO Importer wasn't registered, skipping unregister.")


if __name__ == "__main__":
    register()  # Registra l'addon
    print("Addon OVO registrato.")

    try:
        import os

        # Ottieni il percorso della cartella in cui si trova lo script attuale
        script_dir = os.path.dirname(os.path.abspath(__file__))

        # Specifica il percorso del file .blend da caricare (modifica secondo le tue necessità)
        blend_path = os.path.join(script_dir, "../scenes", "scarpa2.blend")

        # Carica la scena
        bpy.ops.wm.open_mainfile(filepath=blend_path)
        print(f"Scena caricata da: {blend_path}")

        # Crea un percorso relativo alla cartella dello script per l'output
        output_path = os.path.join(script_dir, "../bin", "output.ovo")

        # Esegui l'export con il percorso relativo e i parametri desiderati
        bpy.ops.export_scene.ovo(
            filepath=output_path,
            use_mesh=True,          # Includi le mesh
            use_light=True,         # Includi le luci
            use_legacy_compression=True  # Usa compressione S3TC
        )
        print(f"Export completato con successo! File salvato in: {output_path}")

    except Exception as e:
        print(f"Errore durante l'export: {e}")
        import traceback
        traceback.print_exc()

    unregister()
    print("Addon OVO deregistrato.")
