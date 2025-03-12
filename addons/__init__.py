"""
OVO Exporter - Blender addon per esportare scene nel formato OVO
Autore: Martina Galasso
Versione: 0.1
"""

bl_info = {
    "name": "OVO Exporter",
    "author": "Martina Galasso",
    "version": (0, 1),
    "blender": (4, 2, 1),
    "location": "File > Export > OverView Object (.ovo)",
    "description": "Export the current scene to the OVO file format",
    "category": "Import-Export",
}

# Importa i moduli necessari
import bpy
from bpy_extras.io_utils import ExportHelper
from bpy.props import StringProperty, BoolProperty, EnumProperty
from bpy.types import Operator, Panel

# Importa i moduli dell'addon

import sys
import os

# Ottieni il percorso assoluto della directory che contiene questo file
current_dir = os.path.dirname(os.path.abspath(__file__))

# Aggiungi questa directory al sys.path se non è già presente
if current_dir not in sys.path:
    sys.path.append(current_dir)

# Importa i moduli dell'addon usando importazioni assolute
from ovo_types import ChunkType, HullType
from ovo_packer import OVOPacker
from ovo_texture_manager import OVOTextureManager
from ovo_exporter_core import OVO_Exporter
from ovo_exporter_ui import OVO_PT_export_main, menu_func_export, register, unregister


def menu_func_export(self, context):
    """Aggiunge la voce di menu per l'esportazione OVO"""
    self.layout.operator(OVO_PT_export_main.bl_idname, text="OverView Object (.ovo)")

def register():
    """Registra l'addon nel sistema di Blender"""
    try:
        bpy.utils.unregister_class(OVO_PT_export_main)
        print("Operator già registrato, deregistrato prima di una nuova registrazione.")
    except RuntimeError:
        print("Operator non era registrato, procedo normalmente.")

    bpy.utils.register_class(OVO_PT_export_main)
    bpy.types.TOPBAR_MT_file_export.append(menu_func_export)
    print("OVO Exporter registrato con successo.")

def unregister():
    """Deregistra l'addon dal sistema di Blender"""
    try:
        bpy.utils.unregister_class(OVO_PT_export_main)
        bpy.types.TOPBAR_MT_file_export.remove(menu_func_export)
        print("OVO Exporter deregistrato con successo.")
    except RuntimeError:
        print("Operator non era registrato, skipping unregister.")

# Questo codice va aggiunto alla fine del file __init__.py o ovo_exporter_ui.py

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
        # Stampa il traceback completo per debug
        import traceback
        traceback.print_exc()

    unregister()
    print("Addon OVO deregistrato.")