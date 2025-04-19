# OVO Exporter/Importer Tool for Blender

OVO Tools is a Blender addon for importing and exporting 3D models in the OVO (OverView Object) file format. This format is designed to store mesh data, materials, textures, lights, and scene hierarchies for use in various 3D applications.

## Features

- Export Blender scenes to OVO format
- Import OVO files into Blender
- Support for mesh geometry with materials
- Support for light types (point, directional, spot)
- Texture handling with compression options
- Support for hierarchical scene structure
- Physics data preservation
- Level of Detail (LOD) generation

## Requirements

- Blender 4.2.1 LTS (supported until 2026)
- Python 3.11 (included with Blender)

## Installation

### As a Blender Addon

1. Download the OVO Tools repository
2. Open Blender
3. Go to Edit > Preferences > Add-ons
4. Click "Install..." and select the `__init__.py` file from the OVO Tools directory
5. Enable the addon by checking the box next to "Import-Export: OVO Tools (Importer & Exporter)"

### For Development Setup

To set up a development environment for working on the OVO Tools codebase:

#### Step 1: Find Blender's Python executable

1. Open Blender
2. Switch to the Scripting workspace
3. Open the Python Console (if not already open)
4. Execute the following commands:

```python
>>> import sys
>>> print(sys.executable)
# Example output: /Applications/Blender.app/Contents/Resources/4.2/python/bin/python3.11
```

5. Note down the path to Blender's Python executable

#### Step 2: Configure your IDE (PyCharm example)

1. Open PyCharm with your project
2. Go to Settings/Preferences > Project: [YourProject] > Python Interpreter
3. Click the gear icon > Add...
4. Select "System Interpreter" and enter the path to Blender's Python executable from Step 1
5. Click OK to save

#### Step 3: Install fake-bpy-module for code completion

Using Blender's Python executable from Step 1:

```bash
/path/to/blender/python -m pip install fake-bpy-module-4.2
```

For example:
```bash
/Applications/Blender.app/Contents/Resources/4.2/python/bin/python3.11 -m pip install fake-bpy-module-4.2
```

On Windows, the path might look like:
```bash
C:\Program Files\Blender Foundation\Blender 4.2\4.2\python\bin\python.exe -m pip install fake-bpy-module-4.2
```

*Note: This provides code completion in your IDE but doesn't affect the actual Blender functionality.*

## Usage

### Running Tests

To run tests, you need to execute the test script through Blender's Python interpreter. Use the following command pattern:

```bash
/path/to/blender --background --python "/path/to/your/test_script.py"
```

For example:
```bash
/Applications/Blender.app/Contents/MacOS/Blender --background --python "/path/to/project/visual_test.py"
```

On Windows:
```bash
"C:\Program Files\Blender Foundation\Blender 4.2\blender.exe" --background --python "C:\path\to\project\visual_test.py"
```

The `--background` flag runs Blender without the GUI, which is useful for automated testing.

### Exporting OVO Files

1. Open your Blender scene
2. Go to File > Export > OverView Object (.ovo)
3. Configure export options:
   - Include Meshes: Export mesh objects
   - Include Lights: Export light objects
   - Use S3TC Compression: Use legacy DXT1/DXT5 compression for textures
   - Flip Textures Vertically: Enable for most game engines
4. Select the destination file path
5. Click "Export OVO"

### Importing OVO Files

1. Go to File > Import > OverView Object (.ovo)
2. Configure import options:
   - Flip Textures: Enable if textures appear upside-down
3. Select the OVO file
4. Click "Import OVO"

## Development

### Project Structure

- `__init__.py`: Main addon initialization
- `ovo_exporter_core.py`: Core exporter functionality
- `ovo_exporter_ui.py`: Exporter UI interface
- `ovo_importer_core.py`: Core importer functionality
- `ovo_importer_ui.py`: Importer UI interface
- `ovo_types.py`: Common data types and constants
- `ovo_*_factory.py`: Object creation utilities
- `ovo_texture_manager.py`: Texture processing
- `ovo_texture_flipper.py`: Texture flipping utility
- `ovo_physics.py`: Physics data handling
- `ovo_lod_manager.py`: LOD generation

### Standalone Operation (Without Blender UI)

The OVO Tools are designed to work in both addon and development environments. The modules include main functions that can be executed directly:

#### Exporter Standalone Mode

The exporter has a built-in main function that can be executed directly from Python without using Blender's UI:

```python
python __init__.py
```

When run this way, the exporter:
- Expects a `scenes/` directory in the project root containing `.blend` files
- Automatically loads the first `.blend` file it finds
- Produces the output `.ovo` file in the `bin/output.ovo` directory
- Uses default export settings (meshes, lights, and legacy compression enabled)

This is particularly useful for:
- Batch processing multiple files
- Automated testing
- Pipeline integration
- Development debugging

#### Importer Standalone Mode

The importer can also be run in standalone mode:

```python
python ovo_importer_core.py /path/to/file.ovo
```

When run this way, the importer:
- Loads the specified OVO file
- Creates a new Blender scene with the imported content
- Automatically handles textures and materials
- Preserves the original scene hierarchy

This standalone operation is useful for:
- Scripted content pipelines
- Automated testing
- Quick previews without using Blender's UI
- Development and debugging

### Visual Testing

The included visual testing framework can be used to verify that export and import operations preserve visual fidelity:

1. Place test `.blend` files in the `scenes` directory
2. Run the test script through Blender as described in the "Running Tests" section
3. Review the HTML test report in the `output/visual_reports` directory

## Troubleshooting

- **Texture issues**: Check the "Flip Textures" option when importing/exporting
- **Missing textures**: Make sure to "Pack Resources" in your Blender project (File > External Data > Pack Resources) to ensure all textures are included in the project
- **Missing materials**: Ensure materials have proper node setups in Blender
- **Console errors**: Run Blender from the command line to see detailed error messages


## Contributors

- Martina Galasso
- Kevin Quarenghi