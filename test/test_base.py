# test_base.py
import unittest
import bpy
import os
import sys
from pathlib import Path

# Aggiungi la directory dei test al path
test_dir = os.path.dirname(os.path.abspath(__file__))
if test_dir not in sys.path:
    sys.path.append(test_dir)

# Importa il parser OVO
from OVO_parser import OVOParser
from test_utils import export_ovo, captured_output


class OVOExporterTestBase(unittest.TestCase):
    """Classe base per tutti i test dell'OVO Exporter"""

    def setUp(self):
        """Configurazione iniziale per ogni test"""
        # Imposta i percorsi di base
        self.test_dir = os.path.dirname(os.path.abspath(__file__))
        self.scenes_dir = os.path.join(self.test_dir, "scenes")
        self.output_dir = os.path.join(self.test_dir, "output")

        # Crea la directory di output se non esiste
        os.makedirs(self.output_dir, exist_ok=True)

        # Inizializza il parser OVO
        self.parser = OVOParser(verbose=False)  # Disabilita anche l'output del parser

    def export_and_parse(self, blend_file, output_name=None):
        """
        Carica una scena .blend, la esporta in formato OVO e parsa il file risultante

        Args:
            blend_file (str): Nome del file .blend nella directory scenes
            output_name (str, optional): Nome del file di output OVO

        Returns:
            dict: Dati di validazione dal parser OVO
        """
        # Imposta il nome del file di output
        if output_name is None:
            output_name = Path(blend_file).stem + ".ovo"

        with captured_output():
            blend_path = os.path.join(self.scenes_dir, blend_file)
            output_path = os.path.join(self.output_dir, output_name)

        # Carica la scena (sopprimendo l'output)
        with captured_output():
            bpy.ops.wm.open_mainfile(filepath=blend_path)

        with captured_output():
            export_ovo(output_path, suppress_output=True)

        # Verifica che il file sia stato creato
        self.assertTrue(os.path.exists(output_path), f"Il file {output_path} non è stato creato")

        # Parsa il file OVO (sopprimendo l'output)
        with captured_output():
            validation_data = self.parser.parse_ovo_file(output_path)

        return validation_data