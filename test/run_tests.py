# run_tests.py
import unittest
import sys
import os
import glob
import importlib.util

# Configurazione dei percorsi
test_dir = os.path.dirname(os.path.abspath(__file__))
if test_dir not in sys.path:
    sys.path.append(test_dir)
cases_dir = os.path.join(test_dir, "cases")
if cases_dir not in sys.path:
    sys.path.append(cases_dir)

# Importa il runner personalizzato
from test_utils import JasmineStyleTextTestRunner


def discover_and_load_tests():
    """Scopre e carica automaticamente tutti i test nella directory cases"""
    suite = unittest.TestSuite()

    # Trova tutti i file di test
    test_files = glob.glob(os.path.join(cases_dir, "test_*.py"))

    for test_file in test_files:
        module_name = os.path.basename(test_file)[:-3]  # Rimuovi .py
        print(f"Trovato modulo di test: {module_name}")

        # Carica il modulo dinamicamente
        spec = importlib.util.spec_from_file_location(module_name, test_file)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        # Trova le classi di test nel modulo
        for item_name in dir(module):
            item = getattr(module, item_name)
            if isinstance(item, type) and issubclass(item, unittest.TestCase) and item != unittest.TestCase:
                print(f"  Aggiunta test class: {item_name}")
                suite.addTest(unittest.defaultTestLoader.loadTestsFromTestCase(item))

    return suite


def run_all_tests():
    # Stampa intestazione
    print("\n==== Test Suite OVO Exporter ====\n")

    # Scopri e carica tutti i test
    suite = discover_and_load_tests()

    # Esegui i test
    runner = JasmineStyleTextTestRunner(verbosity=1)
    result = runner.run(suite)

    # Restituisci un codice di uscita per l'integrazione CI
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(run_all_tests())