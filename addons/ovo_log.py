# ================================================================
# LOGGING UTILITY
# ================================================================
# Centralized logging for OVO Tools (import/export).
# Provides a single `log()` function for unified formatting,
# indentation, and ANSI coloring across modules.
# ================================================================

# --------------------------------------------------------
# Imports
# --------------------------------------------------------
try:
    from .ovo_types import GREEN, YELLOW, BLUE, RED, MAGENTA,RESET, BOLD
except ImportError:
    from ovo_types import GREEN, YELLOW, BLUE, RED, MAGENTA, RESET, BOLD

# --------------------------------------------------------
# Logging Function
# --------------------------------------------------------
def log(message: str, category: str = "", indent: int = 0):
    """
    Print a formatted log message with ANSI color and indentation based on entity category.

    Args:
        message (str): The message to log.
        category (str): Entity category or warning type. One of:
            "MESH"    - Mesh operations (green)
            "LIGHT"   - Light operations (yellow)
            "NODE"    - Generic node operations (blue)
            "WARNING" - Warning messages (red)
            "ERROR"   - Error messages (red)
            ""        - No tag, no color (plain output)
        indent (int): Number of indentation levels to apply.
    """

    # If no category is provided, print plain text
    if not category:
        print("  " * indent + message)
        return

    # Map categories to ANSI color codes from ovo_types
    color_map = {
        "MESH": GREEN,
        "LIGHT": YELLOW,
        "NODE": BLUE,
        "MATERIAL": MAGENTA,
        "WARNING": RED,
        "ERROR": RED
    }
    # Determine the color for the given category; default to node color
    color = color_map.get(category.upper(), BLUE)

    indent_str = "  " * indent

    print(f"{BOLD}{color}[{category.upper()}]{RESET} {indent_str}{message}")