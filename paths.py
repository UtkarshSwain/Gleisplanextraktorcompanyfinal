"""
Centralized path resolution for RailDoc Studio.
Handles both development and portable/bundled distribution modes.

In portable/bundled mode:
- BUNDLED_DIR: Read-only resources (models, profiles, tools)
- USER_DATA_DIR: Writable user data (databases, configs)

Usage:
    from paths import get_model_path, get_database_path, BUNDLED_DIR
    model = YOLO(str(get_model_path("wienschwarz.pt")))
"""
import os
import sys
from pathlib import Path


def is_bundled() -> bool:
    """Check if running as PyInstaller bundle or portable distribution."""
    return getattr(sys, 'frozen', False)


def get_bundled_dir() -> Path:
    """
    Get directory for bundled READ-ONLY resources.
    - In bundle/portable: Directory where the app is located
    - In dev: Project root
    """
    if is_bundled():
        # PyInstaller bundle
        return Path(sys._MEIPASS)
    # Development mode - use directory where this file is located
    return Path(__file__).parent


def get_user_data_dir() -> Path:
    """
    Get directory for WRITABLE user data (databases, configs).
    - In bundle/portable: Next to the executable (portable mode)
    - In dev: Project root
    """
    if is_bundled():
        # Get directory where .exe is located (portable mode)
        return Path(sys.executable).parent / "RailDocStudio_Data"
    # Development mode - use project root
    return Path(__file__).parent


def get_app_data_dir() -> Path:
    """
    Alternative: Use Windows AppData for user data.
    %LOCALAPPDATA%\\RailDocStudio\\
    """
    if sys.platform == 'win32':
        app_data = Path(os.environ.get('LOCALAPPDATA', ''))
        if app_data.exists():
            return app_data / "RailDocStudio"
    return get_user_data_dir()


# ============================================================================
# GLOBAL PATH CONSTANTS
# ============================================================================

BUNDLED_DIR = get_bundled_dir()
USER_DATA_DIR = get_user_data_dir()

# Ensure user data directory exists
try:
    USER_DATA_DIR.mkdir(parents=True, exist_ok=True)
except Exception:
    pass  # May fail in some environments, will be created later


# ============================================================================
# BUNDLED RESOURCES (READ-ONLY)
# ============================================================================

def get_model_path(model_name: str = "wienschwarz.pt") -> Path:
    """Get path to YOLO model file."""
    return BUNDLED_DIR / "Gleisplanextraktoryolomodel" / model_name


def get_profile_path(profile_name: str = "wien_track_plans.yaml") -> Path:
    """Get path to profile YAML file."""
    return BUNDLED_DIR / "profiles" / profile_name


def get_profiles_dir() -> Path:
    """Get profiles directory."""
    return BUNDLED_DIR / "profiles"


def get_tesseract_path() -> Path:
    """Get path to tesseract.exe."""
    if is_bundled():
        return BUNDLED_DIR / "tesseract" / "tesseract.exe"
    # Development mode - check venv first
    venv_path = BUNDLED_DIR / "venv" / "tesseract" / "tesseract.exe"
    if venv_path.exists():
        return venv_path
    # Fallback for portable dev structure
    return BUNDLED_DIR / "tesseract" / "tesseract.exe"


def get_poppler_path() -> Path:
    """Get path to poppler bin directory."""
    if is_bundled():
        return BUNDLED_DIR / "poppler"
    # Development mode - check venv first (multiple possible names)
    for poppler_name in ["poppler-25.12.0", "poppler-24.08.0", "poppler"]:
        venv_path = BUNDLED_DIR / "venv" / poppler_name / "Library" / "bin"
        if venv_path.exists():
            return venv_path
    # Fallback for portable dev structure
    return BUNDLED_DIR / "poppler"


# ============================================================================
# USER DATA (WRITABLE)
# ============================================================================

def get_database_path() -> Path:
    """Get path to main SQLite database."""
    data_dir = USER_DATA_DIR / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "gleisplanextraktor.db"


def get_track_layouts_db_path() -> Path:
    """Get path to track layouts database."""
    return USER_DATA_DIR / "track_layouts.db"


def get_custom_symbols_path() -> Path:
    """Get path to custom_symbols.json."""
    return USER_DATA_DIR / "custom_symbols.json"


def get_ocr_adjustments_path() -> Path:
    """Get path to OCR adjustments config."""
    config_dir = USER_DATA_DIR / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir / "ocr_adjustments.json"


def get_export_templates_path() -> Path:
    """Get path to export templates."""
    return USER_DATA_DIR / "export_templates.json"


def get_custom_symbol_templates_dir(symbol_name: str) -> Path:
    """Get directory for custom symbol templates."""
    templates_dir = USER_DATA_DIR / "custom_symbol_templates" / symbol_name
    templates_dir.mkdir(parents=True, exist_ok=True)
    return templates_dir


def get_training_data_dir() -> Path:
    """Get directory for new symbol training data."""
    training_dir = USER_DATA_DIR / "training_data" / "new_symbols"
    training_dir.mkdir(parents=True, exist_ok=True)
    return training_dir


def get_debug_dir() -> Path:
    """Get directory for debug output files."""
    debug_dir = USER_DATA_DIR / "debug"
    debug_dir.mkdir(parents=True, exist_ok=True)
    return debug_dir


def get_debug_file_path(filename: str = "debug.txt") -> Path:
    """Get path for a debug output file."""
    return get_debug_dir() / filename
