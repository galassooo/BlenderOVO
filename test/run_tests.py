#!/usr/bin/env python3
"""
Simplified test runner for OVO Tools visual tests.
This script discovers and runs all visual tests in a Blender environment.
"""

import os
import sys
import unittest
import subprocess
import importlib.util

# Configure paths
test_dir = os.path.dirname(os.path.abspath(__file__))
if test_dir not in sys.path:
    sys.path.append(test_dir)


def run_visual_tests():
    """Runs the visual tests for OVO Tools."""
    print("\n==== OVO Tools Visual Test Suite ====\n")

    # Import the visual test module
    try:
        from visual_test import VisualTest
        # Create a test suite with our visual tests
        suite = unittest.TestSuite()
        suite.addTest(unittest.defaultTestLoader.loadTestsFromTestCase(VisualTest))

        # Run the tests
        runner = unittest.TextTestRunner(verbosity=2)
        result = runner.run(suite)

        # Return exit code
        return 0 if result.wasSuccessful() else 1
    except ImportError as e:
        print(f"Error importing test module: {e}")
        return 1


def run_tests_in_blender():
    """Launches Blender to run the tests (for command line execution)."""
    blender_path = os.environ.get('BLENDER_PATH', 'blender')

    try:
        # Start Blender in background mode and run the tests
        cmd = [
            blender_path,
            "--background",
            "--python-expr",
            "import sys; sys.path.append('{}'); from run_tests import run_visual_tests; sys.exit(run_visual_tests())".format(
                test_dir.replace('\\', '\\\\')
            )
        ]

        # Execute Blender
        result = subprocess.run(cmd, check=True)
        return result.returncode

    except subprocess.CalledProcessError as e:
        print(f"Error running tests in Blender: {e}")
        return e.returncode

    except Exception as e:
        print(f"Unexpected error: {e}")
        return 1


if __name__ == "__main__":
    # If running inside Blender, sys.executable will contain 'blender'
    # Otherwise, we need to launch Blender
    if 'blender' in sys.executable.lower():
        sys.exit(run_visual_tests())
    else:
        sys.exit(run_tests_in_blender())