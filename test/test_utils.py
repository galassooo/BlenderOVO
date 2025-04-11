# test_utils.py
import unittest
import sys
import os
import time
import io
import contextlib


# Colori ANSI
class Colors:
    HEADER = '\033[95m'  # Viola
    BLUE = '\033[94m'  # Blu
    GREEN = '\033[92m'  # Verde
    YELLOW = '\033[93m'  # Giallo
    RED = '\033[91m'  # Rosso
    ENDC = '\033[0m'  # Resetta colore
    BOLD = '\033[1m'  # Grassetto
    UNDERLINE = '\033[4m'  # Sottolineato


@contextlib.contextmanager
def captured_output():
    """
    Context manager for capturing stdout and stderr.
    Designed to suppress output during operations.
    """
    # Capture both stdout and stderr
    old_stdout, old_stderr = sys.stdout, sys.stderr
    out, err = io.StringIO(), io.StringIO()
    try:
        sys.stdout = out
        sys.stderr = err
        yield out, err
    finally:
        # Restore original streams
        sys.stdout, sys.stderr = old_stdout, old_stderr

class JasmineStyleTextTestResult(unittest.TextTestResult):
    """
    Runner di test personalizzato con output in stile Jasmine e colori
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.startTime = time.time()
        self.tests_run = 0
        self.successes = []

    def startTest(self, test):
        super().startTest(test)
        self.tests_run += 1
        # Non stampiamo nulla qui, accumuliamo il risultato

    def addSuccess(self, test):
        super().addSuccess(test)
        self.successes.append(test)

        # Stampa il risultato dopo aver determinato il successo
        test_name = test._testMethodName.replace('test_', '').replace('_', ' ').title()
        self.stream.write(f"  {Colors.BOLD}{test_name}{Colors.ENDC} ... {Colors.GREEN}✓{Colors.ENDC}\n")

        # Ottieni la descrizione del test dal docstring
        docstring = test._testMethodDoc
        if docstring:
            self.stream.write(f"    {Colors.BLUE}•{Colors.ENDC} {docstring}\n")

        self.stream.flush()

    def addError(self, test, err):
        # Stampa il risultato prima che super().addError aggiunga i dettagli dell'errore
        test_name = test._testMethodName.replace('test_', '').replace('_', ' ').title()
        self.stream.write(f"  {Colors.BOLD}{test_name}{Colors.ENDC} ... {Colors.RED}✗ (errore){Colors.ENDC}\n")

        super().addError(test, err)
        self.stream.flush()

    def addFailure(self, test, err):
        # Stampa il risultato prima che super().addFailure aggiunga i dettagli del fallimento
        test_name = test._testMethodName.replace('test_', '').replace('_', ' ').title()
        self.stream.write(f"  {Colors.BOLD}{test_name}{Colors.ENDC} ... {Colors.YELLOW}✗ (fallito){Colors.ENDC}\n")

        super().addFailure(test, err)
        self.stream.flush()


class JasmineStyleTextTestRunner(unittest.TextTestRunner):
    """
    Runner di test personalizzato con output in stile Jasmine
    """

    def __init__(self, stream=None, descriptions=True, verbosity=1,
                 failfast=False, buffer=False, resultclass=None):
        if resultclass is None:
            resultclass = JasmineStyleTextTestResult
        super().__init__(stream, descriptions, verbosity,
                         failfast, buffer, resultclass)

    def run(self, test):
        "Run the given test case or test suite."
        # Stampa l'intestazione dei test
        self.stream.writeln(f"\n{Colors.HEADER}{Colors.BOLD}==== OVO Exporter Test Suite ===={Colors.ENDC}")

        start_time = time.time()
        result = super().run(test)
        end_time = time.time()

        # Calcola il tempo totale
        total_time = end_time - start_time

        # Stampa il riepilogo
        self.stream.writeln(f"\n{Colors.BOLD}=== Riepilogo ==={Colors.ENDC}")

        passed = result.testsRun - len(result.failures) - len(result.errors)
        self.stream.writeln(f"  {Colors.GREEN}✓ Passati: {passed}{Colors.ENDC}")

        if result.failures:
            self.stream.writeln(f"  {Colors.YELLOW}✗ Falliti: {len(result.failures)}{Colors.ENDC}")

        if result.errors:
            self.stream.writeln(f"  {Colors.RED}✗ Errori: {len(result.errors)}{Colors.ENDC}")

        self.stream.writeln(f"\n{Colors.BOLD}Tempo totale:{Colors.ENDC} {Colors.BLUE}{total_time:.3f}s{Colors.ENDC}")

        return result


def export_ovo(output_path, use_mesh=True, use_light=True, use_legacy_compression=True, suppress_output=True):
    """
    Esporta la scena corrente in formato OVO

    Args:
        output_path: Percorso dove salvare il file OVO
        use_mesh: Includere le mesh nell'export
        use_light: Includere le luci nell'export
        use_legacy_compression: Usare la compressione legacy
        suppress_output: Se True, sopprime l'output dell'esportazione

    Returns:
        bool: True se l'export è riuscito, False altrimenti
    """
    import bpy
    try:
        if suppress_output:
            with captured_output():
                bpy.ops.export_scene.ovo(
                    filepath=output_path,
                    use_mesh=use_mesh,
                    use_light=use_light,
                    use_legacy_compression=use_legacy_compression
                )
        else:
            bpy.ops.export_scene.ovo(
                filepath=output_path,
                use_mesh=use_mesh,
                use_light=use_light,
                use_legacy_compression=use_legacy_compression
            )
        return True
    except Exception as e:
        # L'errore dovrebbe essere sempre visibile, anche se l'output è soppresso
        print(f"{Colors.RED}Errore durante l'export: {e}{Colors.ENDC}")
        return False