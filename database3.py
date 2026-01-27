# database3.py - SQLite version for local development (no Docker/PostgreSQL required)
"""
SQLite-based database module for railway detection system.
This version works on laptops without Docker or PostgreSQL.

Features:
- Local SQLite database file
- All functionality from PostgreSQL version
- No external dependencies (sqlite3 is built-in)
"""

import sqlite3
import json
import os
import numpy as np
import base64
import zlib
from contextlib import contextmanager
from typing import Optional, Tuple, List, Dict
from datetime import datetime

try:
    import psutil  # For memory monitoring (optional)
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

# ============================================================================
# DATABASE CONFIGURATION
# ============================================================================

# Database file path - can be set via environment variable or defaults to local file
DB_PATH = os.environ.get("DATABASE_PATH", os.path.join(os.path.dirname(__file__), "track_layouts.db"))


def get_memory_usage():
    """Get current memory usage in MB"""
    if HAS_PSUTIL:
        process = psutil.Process(os.getpid())
        mem_mb = process.memory_info().rss / 1024 / 1024
        return mem_mb
    return 0.0


def log_memory(prefix: str = ""):
    """Print current memory usage"""
    if HAS_PSUTIL:
        mem_mb = get_memory_usage()
        print(f"[MEM] {prefix}: {mem_mb:.1f} MB")


class DictCursor:
    """
    Wrapper to make sqlite3 cursor return dict-like results.
    Mimics psycopg2's RealDictCursor behavior.
    """
    def __init__(self, cursor):
        self._cursor = cursor
        self._description = None

    def execute(self, sql, params=None):
        if params:
            self._cursor.execute(sql, params)
        else:
            self._cursor.execute(sql)
        self._description = self._cursor.description
        return self

    def fetchone(self):
        row = self._cursor.fetchone()
        if row is None:
            return None
        return self._row_to_dict(row)

    def fetchall(self):
        rows = self._cursor.fetchall()
        return [self._row_to_dict(row) for row in rows]

    def _row_to_dict(self, row):
        if self._description is None:
            return None
        return {desc[0]: value for desc, value in zip(self._description, row)}

    @property
    def lastrowid(self):
        return self._cursor.lastrowid


def get_connection():
    """Establishes a connection to the SQLite database."""
    # Ensure directory exists
    db_dir = os.path.dirname(DB_PATH)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
    # Enable foreign keys
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def db_cursor(commit=False):
    """A helper to manage database connections and cursors safely."""
    conn = get_connection()
    try:
        cursor = DictCursor(conn.cursor())
        yield cursor
        if commit:
            conn.commit()
    finally:
        conn.close()


def init_db():
    """
    Initializes the database by creating tables if they don't exist.
    Includes validation, quality metrics, and manual corrections tables.
    """
    sql_create_layouts_table = """
    CREATE TABLE IF NOT EXISTS track_layouts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        layout_name TEXT UNIQUE NOT NULL
    );
    """

    sql_create_workspaces_table = """
    CREATE TABLE IF NOT EXISTS workspaces (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        layout_id INTEGER UNIQUE NOT NULL REFERENCES track_layouts(id) ON DELETE CASCADE,
        edited_data_json TEXT NOT NULL,
        track_skeleton TEXT,
        image_dimensions TEXT,
        last_modified TEXT DEFAULT CURRENT_TIMESTAMP
    );
    """

    # Validation log table
    sql_create_validation_log = """
    CREATE TABLE IF NOT EXISTS validation_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        layout_id INTEGER NOT NULL REFERENCES track_layouts(id) ON DELETE CASCADE,
        validation_type TEXT NOT NULL,
        severity TEXT CHECK (severity IN ('ERROR', 'WARNING', 'INFO')),
        message TEXT NOT NULL,
        row_id INTEGER,
        details TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    """

    # Data quality metrics table
    sql_create_quality_metrics = """
    CREATE TABLE IF NOT EXISTS quality_metrics (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        layout_id INTEGER NOT NULL REFERENCES track_layouts(id) ON DELETE CASCADE,
        metric_name TEXT NOT NULL,
        metric_value REAL,
        metric_data TEXT,
        computed_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    """

    # Manual corrections log table
    sql_create_manual_corrections = """
    CREATE TABLE IF NOT EXISTS manual_corrections (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        layout_id INTEGER NOT NULL REFERENCES track_layouts(id) ON DELETE CASCADE,
        row_id INTEGER NOT NULL,
        column_name TEXT NOT NULL,
        old_value TEXT,
        new_value TEXT,
        correction_type TEXT,
        corrected_by TEXT DEFAULT 'user',
        correction_reason TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    """

    # Custom symbols table (for template matching)
    sql_create_custom_symbols = """
    CREATE TABLE IF NOT EXISTS custom_symbols (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol_name TEXT UNIQUE NOT NULL,
        config_json TEXT NOT NULL,
        templates_data BLOB,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    """

    # Create indexes for performance
    sql_create_indexes = [
        "CREATE INDEX IF NOT EXISTS idx_validation_log_layout ON validation_log(layout_id);",
        "CREATE INDEX IF NOT EXISTS idx_validation_log_severity ON validation_log(severity);",
        "CREATE INDEX IF NOT EXISTS idx_quality_metrics_layout ON quality_metrics(layout_id);",
        "CREATE INDEX IF NOT EXISTS idx_quality_metrics_name ON quality_metrics(metric_name);",
        "CREATE INDEX IF NOT EXISTS idx_manual_corrections_layout ON manual_corrections(layout_id);",
        "CREATE INDEX IF NOT EXISTS idx_manual_corrections_column ON manual_corrections(column_name);",
        "CREATE INDEX IF NOT EXISTS idx_manual_corrections_created ON manual_corrections(created_at);",
    ]

    try:
        conn = get_connection()
        cursor = conn.cursor()

        print("Initializing SQLite database tables...")
        cursor.execute(sql_create_layouts_table)
        cursor.execute(sql_create_workspaces_table)
        cursor.execute(sql_create_validation_log)
        cursor.execute(sql_create_quality_metrics)
        cursor.execute(sql_create_manual_corrections)
        cursor.execute(sql_create_custom_symbols)

        # Create indexes
        for index_sql in sql_create_indexes:
            cursor.execute(index_sql)

        # Create correction statistics view
        cursor.execute("""
        CREATE VIEW IF NOT EXISTS correction_statistics AS
        SELECT
            t.layout_name,
            mc.column_name,
            COUNT(*) as correction_count,
            COUNT(DISTINCT mc.row_id) as affected_rows,
            MIN(mc.created_at) as first_correction,
            MAX(mc.created_at) as last_correction
        FROM manual_corrections mc
        JOIN track_layouts t ON mc.layout_id = t.id
        GROUP BY t.layout_name, mc.column_name;
        """)

        conn.commit()
        conn.close()

        print(f"Database initialized at: {DB_PATH}")
        print("Tables are ready (including validation and correction tracking).")
    except Exception as e:
        print(f"Error initializing database: {e}")
        raise


def compress_track_skeleton(skeleton: np.ndarray) -> str:
    """
    Compress track skeleton using sparse representation + zlib.

    Strategy:
    1. Store only non-zero coordinates (sparse format)
    2. Compress with zlib (level 9)
    3. Encode as base64

    Typical compression: 10MB -> 50KB (200x smaller!)
    """
    log_memory("Before compression")

    try:
        # Get non-zero coordinates (sparse representation)
        nonzero_y, nonzero_x = np.nonzero(skeleton)

        # Store shape + coordinates as compact format
        h, w = skeleton.shape
        data = {
            'shape': [int(h), int(w)],
            'coords': [nonzero_y.tolist(), nonzero_x.tolist()]
        }

        # Serialize to JSON
        json_str = json.dumps(data, separators=(',', ':'))  # No whitespace
        json_bytes = json_str.encode('utf-8')

        # Compress with zlib (max compression)
        compressed = zlib.compress(json_bytes, level=9)

        # Encode as base64
        b64_str = base64.b64encode(compressed).decode('utf-8')

        # Calculate compression ratio
        original_size = skeleton.nbytes
        compressed_size = len(b64_str)
        ratio = original_size / max(compressed_size, 1)

        log_memory("After compression")
        print(f"  Track skeleton compressed: {original_size/1024/1024:.1f}MB -> {compressed_size/1024:.1f}KB ({ratio:.0f}x)")

        return b64_str

    except Exception as e:
        print(f"  Compression failed: {e}")
        return None


def decompress_track_skeleton(compressed_str: str) -> Optional[np.ndarray]:
    """
    Decompress track skeleton from compressed sparse format.
    """
    log_memory("Before decompression")

    try:
        # Decode from base64
        compressed_bytes = base64.b64decode(compressed_str)

        # Decompress with zlib
        json_bytes = zlib.decompress(compressed_bytes)

        # Parse JSON
        json_str = json_bytes.decode('utf-8')
        data = json.loads(json_str)

        # Reconstruct sparse array
        h, w = data['shape']
        coords_y, coords_x = data['coords']

        # Create empty array
        skeleton = np.zeros((h, w), dtype=np.uint8)

        # Fill non-zero coordinates
        skeleton[coords_y, coords_x] = 255

        log_memory("After decompression")
        print(f"  Track skeleton decompressed: {skeleton.shape}")

        return skeleton

    except Exception as e:
        print(f"  Decompression failed: {e}")
        return None


def get_workspace_data(layout_name: str) -> Optional[Tuple[List[Dict], Optional[np.ndarray], Optional[Dict]]]:
    """
    Retrieves the saved workspace JSON data, track skeleton, and image dimensions.

    Returns:
        Tuple of (data_list, track_skeleton, image_dimensions) or None if not found
    """
    log_memory(f"Loading workspace: {layout_name}")
    print(f"Checking database for workspace: {layout_name}")

    sql_query = """
    SELECT w.edited_data_json, w.track_skeleton, w.image_dimensions
    FROM workspaces w
    JOIN track_layouts t ON w.layout_id = t.id
    WHERE t.layout_name = ?;
    """

    with db_cursor() as cursor:
        cursor.execute(sql_query, (layout_name,))
        result = cursor.fetchone()

        if result:
            print(f"Found saved data for {layout_name}.")

            # Get and parse the JSON data
            workspace_data_raw = result['edited_data_json']
            workspace_data = json.loads(workspace_data_raw) if isinstance(workspace_data_raw, str) else workspace_data_raw

            # Decompress track skeleton if present
            track_skeleton = None
            track_skeleton_compressed = result.get('track_skeleton')

            if track_skeleton_compressed:
                try:
                    track_skeleton = decompress_track_skeleton(track_skeleton_compressed)
                except Exception as e:
                    print(f"  Could not load track skeleton: {e}")
                    track_skeleton = None
            else:
                print(f"  No track skeleton saved for this layout")

            # Parse image dimensions
            image_dimensions = None
            image_dimensions_json = result.get('image_dimensions')

            if image_dimensions_json:
                try:
                    # Parse JSON and convert string keys back to integers
                    dimensions_dict = json.loads(image_dimensions_json) if isinstance(image_dimensions_json, str) else image_dimensions_json
                    image_dimensions = {int(k): v for k, v in dimensions_dict.items()}
                    print(f"  Loaded image dimensions: {image_dimensions}")
                except Exception as e:
                    print(f"  Could not parse image dimensions: {e}")
                    image_dimensions = None
            else:
                print(f"  No image dimensions saved for this layout")

            log_memory("Workspace loaded")
            return workspace_data, track_skeleton, image_dimensions
        else:
            print(f"No saved data found for {layout_name}.")
            return None


def save_workspace_data(layout_name: str, workspace_data: List[Dict],
                       track_skeleton: Optional[np.ndarray] = None,
                       image_dimensions: Optional[dict] = None):
    """
    Saves (Inserts or Updates) the workspace data, track skeleton, and image dimensions.

    Args:
        layout_name: Unique identifier for the layout
        workspace_data: List of detection dictionaries
        track_skeleton: Optional track centerline mask (numpy array)
        image_dimensions: Optional dict of {page_num: {'width': w, 'height': h}}
    """
    log_memory(f"Saving workspace: {layout_name}")

    # Custom JSON encoder for numpy types
    class NumpyEncoder(json.JSONEncoder):
        def default(self, obj):
            if isinstance(obj, np.ndarray):
                return obj.tolist()
            if isinstance(obj, np.integer):
                return int(obj)
            if isinstance(obj, np.floating):
                return float(obj)
            if isinstance(obj, np.bool_):
                return bool(obj)
            return super().default(obj)

    # Convert workspace data to JSON string with numpy handling
    try:
        data_as_json_string = json.dumps(workspace_data, cls=NumpyEncoder)
    except Exception as e:
        print(f"Failed to serialize workspace data: {e}")
        raise

    # Compress track skeleton if present
    track_skeleton_compressed = None
    if track_skeleton is not None:
        track_skeleton_compressed = compress_track_skeleton(track_skeleton)

    # Convert image dimensions to JSON with proper type handling
    image_dimensions_json = None
    if image_dimensions:
        try:
            dimensions_dict = {}
            for page_num, dims in image_dimensions.items():
                dimensions_dict[str(page_num)] = {
                    'width': int(dims['width']) if isinstance(dims['width'], (np.integer, np.int64, np.int32)) else dims['width'],
                    'height': int(dims['height']) if isinstance(dims['height'], (np.integer, np.int64, np.int32)) else dims['height']
                }
            image_dimensions_json = json.dumps(dimensions_dict)
        except Exception as e:
            print(f"Failed to serialize image dimensions: {e}")
            image_dimensions_json = None

    print(f"Saving workspace for {layout_name}...")
    if image_dimensions:
        print(f"  Image dimensions: {image_dimensions}")

    conn = get_connection()
    cursor = conn.cursor()

    try:
        # Ensure layout exists
        cursor.execute(
            "INSERT OR IGNORE INTO track_layouts (layout_name) VALUES (?)",
            (layout_name,)
        )

        # Get layout ID
        cursor.execute("SELECT id FROM track_layouts WHERE layout_name = ?", (layout_name,))
        layout_id_result = cursor.fetchone()
        if not layout_id_result:
            raise Exception(f"Could not create or find layout_id for {layout_name}")
        layout_id = layout_id_result[0]

        # Upsert workspace data + track skeleton + image dimensions
        cursor.execute("""
            INSERT INTO workspaces (layout_id, edited_data_json, track_skeleton, image_dimensions, last_modified)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(layout_id) DO UPDATE SET
                edited_data_json = excluded.edited_data_json,
                track_skeleton = excluded.track_skeleton,
                image_dimensions = excluded.image_dimensions,
                last_modified = excluded.last_modified
        """, (layout_id, data_as_json_string, track_skeleton_compressed, image_dimensions_json, datetime.now().isoformat()))

        conn.commit()
    finally:
        conn.close()

    log_memory("Workspace saved")
    print(f"Saved workspace for {layout_name} (track: {track_skeleton is not None}, dims: {image_dimensions is not None}).")


def delete_workspace_data(layout_name: str) -> bool:
    """
    Delete workspace data for a specific layout.
    This clears the cached analysis results, forcing a full re-analysis on next run.

    Args:
        layout_name: Unique identifier for the layout

    Returns:
        True if deletion was successful, False otherwise
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()

        # Get layout ID
        cursor.execute("SELECT id FROM track_layouts WHERE layout_name = ?", (layout_name,))
        layout_id_result = cursor.fetchone()

        if not layout_id_result:
            print(f"No layout found with name: {layout_name}")
            conn.close()
            return False

        layout_id = layout_id_result[0]

        # Delete workspace data
        cursor.execute("DELETE FROM workspaces WHERE layout_id = ?", (layout_id,))
        conn.commit()
        conn.close()

        print(f"Deleted workspace cache for: {layout_name}")
        return True

    except Exception as e:
        print(f"Failed to delete workspace data: {e}")
        return False


# ============================================================================
# VALIDATION FUNCTIONS
# ============================================================================

def save_validation_results(layout_name: str, validation_results: List):
    """
    Save validation results to database.

    Args:
        layout_name: Layout identifier
        validation_results: List of ValidationResult objects
    """
    conn = get_connection()
    cursor = conn.cursor()

    try:
        # Get layout ID
        cursor.execute("SELECT id FROM track_layouts WHERE layout_name = ?", (layout_name,))
        layout_id_result = cursor.fetchone()

        if not layout_id_result:
            print(f"Layout {layout_name} not found in database")
            conn.close()
            return

        layout_id = layout_id_result[0]

        # Clear old results
        cursor.execute("DELETE FROM validation_log WHERE layout_id = ?", (layout_id,))

        # Insert new results
        for result in validation_results:
            validation_type = result.message.split(':')[0] if ':' in result.message else 'general'

            cursor.execute("""
                INSERT INTO validation_log (layout_id, validation_type, severity, message, row_id, details)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                layout_id,
                validation_type,
                result.severity,
                result.message,
                result.row_id,
                json.dumps(result.details) if result.details else None
            ))

        conn.commit()
        print(f"Saved {len(validation_results)} validation results for {layout_name}")
    finally:
        conn.close()


def get_validation_results(layout_name: str) -> List[Dict]:
    """
    Retrieve validation results for a layout.

    Returns:
        List of validation result dictionaries
    """
    sql_query = """
    SELECT v.validation_type, v.severity, v.message, v.row_id, v.details, v.created_at
    FROM validation_log v
    JOIN track_layouts t ON v.layout_id = t.id
    WHERE t.layout_name = ?
    ORDER BY v.severity DESC, v.created_at DESC;
    """

    with db_cursor() as cursor:
        cursor.execute(sql_query, (layout_name,))
        results = cursor.fetchall()
        return results


def save_quality_metrics(layout_name: str, metrics: Dict):
    """
    Save data quality metrics to database.

    Args:
        layout_name: Layout identifier
        metrics: Dictionary of metric_name -> metric_value/data
    """
    conn = get_connection()
    cursor = conn.cursor()

    try:
        # Get layout ID
        cursor.execute("SELECT id FROM track_layouts WHERE layout_name = ?", (layout_name,))
        layout_id_result = cursor.fetchone()

        if not layout_id_result:
            print(f"Layout {layout_name} not found in database")
            conn.close()
            return

        layout_id = layout_id_result[0]

        # Insert metrics
        for metric_name, metric_info in metrics.items():
            if isinstance(metric_info, dict):
                metric_value = metric_info.get('value')
                metric_data = json.dumps(metric_info.get('data', {}))
            else:
                metric_value = float(metric_info) if isinstance(metric_info, (int, float)) else None
                metric_data = None

            cursor.execute("""
                INSERT INTO quality_metrics (layout_id, metric_name, metric_value, metric_data)
                VALUES (?, ?, ?, ?)
            """, (layout_id, metric_name, metric_value, metric_data))

        conn.commit()
        print(f"Saved {len(metrics)} quality metrics for {layout_name}")
    finally:
        conn.close()


def get_quality_metrics(layout_name: str, metric_name: Optional[str] = None) -> List[Dict]:
    """
    Retrieve quality metrics for a layout.

    Args:
        layout_name: Layout identifier
        metric_name: Optional specific metric to retrieve

    Returns:
        List of metric dictionaries
    """
    if metric_name:
        sql_query = """
        SELECT q.metric_name, q.metric_value, q.metric_data, q.computed_at
        FROM quality_metrics q
        JOIN track_layouts t ON q.layout_id = t.id
        WHERE t.layout_name = ? AND q.metric_name = ?
        ORDER BY q.computed_at DESC;
        """
        params = (layout_name, metric_name)
    else:
        sql_query = """
        SELECT q.metric_name, q.metric_value, q.metric_data, q.computed_at
        FROM quality_metrics q
        JOIN track_layouts t ON q.layout_id = t.id
        WHERE t.layout_name = ?
        ORDER BY q.metric_name, q.computed_at DESC;
        """
        params = (layout_name,)

    with db_cursor() as cursor:
        cursor.execute(sql_query, params)
        results = cursor.fetchall()
        return results


def get_validation_summary(layout_name: str) -> Dict:
    """
    Get a summary of validation results for a layout.

    Returns:
        Dictionary with counts by severity
    """
    sql_query = """
    SELECT v.severity, COUNT(*) as count
    FROM validation_log v
    JOIN track_layouts t ON v.layout_id = t.id
    WHERE t.layout_name = ?
    GROUP BY v.severity;
    """

    with db_cursor() as cursor:
        cursor.execute(sql_query, (layout_name,))
        results = cursor.fetchall()

        summary = {
            'ERROR': 0,
            'WARNING': 0,
            'INFO': 0,
            'total': 0
        }

        for row in results:
            severity = row['severity']
            count = row['count']
            summary[severity] = count
            summary['total'] += count

        return summary


# ============================================================================
# MANUAL CORRECTION FUNCTIONS
# ============================================================================

def log_manual_correction(
    layout_name: str,
    row_id: int,
    column_name: str,
    old_value,
    new_value,
    correction_type: str = 'manual_edit',
    corrected_by: str = 'user',
    correction_reason: Optional[str] = None
):
    """
    Log a manual correction to the database.

    Args:
        layout_name: Layout identifier
        row_id: Row index in the DataFrame
        column_name: Name of the column that was corrected
        old_value: Original value before correction
        new_value: New value after correction
        correction_type: Type of correction (e.g., 'ocr_fix', 'bbox_adjustment', 'class_change')
        corrected_by: User who made the correction
        correction_reason: Optional reason for the correction
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()

        # Get layout ID
        cursor.execute("SELECT id FROM track_layouts WHERE layout_name = ?", (layout_name,))
        layout_id_result = cursor.fetchone()

        if not layout_id_result:
            print(f"Layout {layout_name} not found in database")
            conn.close()
            return

        layout_id = layout_id_result[0]

        # Convert values to strings for storage
        old_value_str = str(old_value) if old_value is not None else None
        new_value_str = str(new_value) if new_value is not None else None

        # Insert correction log
        cursor.execute("""
            INSERT INTO manual_corrections
                (layout_id, row_id, column_name, old_value, new_value, correction_type, corrected_by, correction_reason)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (layout_id, row_id, column_name, old_value_str, new_value_str, correction_type, corrected_by, correction_reason))

        conn.commit()
        conn.close()

        print(f"Logged correction: Row {row_id}, {column_name}: {old_value} -> {new_value}")

    except Exception as e:
        print(f"Error logging manual correction: {e}")


def get_correction_history(layout_name: str, row_id: Optional[int] = None) -> List[Dict]:
    """
    Retrieve correction history for a layout.

    Args:
        layout_name: Layout identifier
        row_id: Optional specific row to filter by

    Returns:
        List of correction dictionaries
    """
    if row_id is not None:
        sql_query = """
        SELECT mc.row_id, mc.column_name, mc.old_value, mc.new_value,
               mc.correction_type, mc.corrected_by, mc.correction_reason, mc.created_at
        FROM manual_corrections mc
        JOIN track_layouts t ON mc.layout_id = t.id
        WHERE t.layout_name = ? AND mc.row_id = ?
        ORDER BY mc.created_at DESC;
        """
        params = (layout_name, row_id)
    else:
        sql_query = """
        SELECT mc.row_id, mc.column_name, mc.old_value, mc.new_value,
               mc.correction_type, mc.corrected_by, mc.correction_reason, mc.created_at
        FROM manual_corrections mc
        JOIN track_layouts t ON mc.layout_id = t.id
        WHERE t.layout_name = ?
        ORDER BY mc.created_at DESC;
        """
        params = (layout_name,)

    with db_cursor() as cursor:
        cursor.execute(sql_query, params)
        results = cursor.fetchall()
        return results


def get_correction_statistics(layout_name: Optional[str] = None) -> List[Dict]:
    """
    Get statistics about corrections.

    Args:
        layout_name: Optional layout to filter by

    Returns:
        List of statistics dictionaries
    """
    if layout_name:
        sql_query = """
        SELECT * FROM correction_statistics
        WHERE layout_name = ?
        ORDER BY correction_count DESC;
        """
        params = (layout_name,)
    else:
        sql_query = """
        SELECT * FROM correction_statistics
        ORDER BY correction_count DESC;
        """
        params = ()

    with db_cursor() as cursor:
        cursor.execute(sql_query, params)
        results = cursor.fetchall()
        return results


def get_most_corrected_fields(layout_name: str, limit: int = 10) -> List[Dict]:
    """
    Get the most frequently corrected fields for a layout.

    Args:
        layout_name: Layout identifier
        limit: Maximum number of results to return

    Returns:
        List of dictionaries with column_name and correction_count
    """
    sql_query = """
    SELECT mc.column_name, COUNT(*) as correction_count,
           COUNT(DISTINCT mc.row_id) as affected_rows
    FROM manual_corrections mc
    JOIN track_layouts t ON mc.layout_id = t.id
    WHERE t.layout_name = ?
    GROUP BY mc.column_name
    ORDER BY correction_count DESC
    LIMIT ?;
    """

    with db_cursor() as cursor:
        cursor.execute(sql_query, (layout_name, limit))
        results = cursor.fetchall()
        return results


def export_corrections_for_retraining(layout_name: str, output_dir: str):
    """
    Export correction data in a format suitable for model retraining.

    Args:
        layout_name: Layout identifier
        output_dir: Directory to save the export files

    Returns:
        Path to the exported JSON file
    """
    from datetime import datetime

    # Get all corrections
    corrections = get_correction_history(layout_name)

    if not corrections:
        print(f"No corrections found for {layout_name}")
        return None

    # Organize by correction type
    export_data = {
        'layout_name': layout_name,
        'export_date': datetime.now().isoformat(),
        'total_corrections': len(corrections),
        'corrections_by_type': {},
        'corrections': corrections
    }

    # Group by correction type
    for corr in corrections:
        corr_type = corr.get('correction_type', 'unknown')
        if corr_type not in export_data['corrections_by_type']:
            export_data['corrections_by_type'][corr_type] = []
        export_data['corrections_by_type'][corr_type].append(corr)

    # Create output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)

    # Generate filename
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"corrections_{layout_name}_{timestamp}.json"
    filepath = os.path.join(output_dir, filename)

    # Write to file
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(export_data, f, indent=2, ensure_ascii=False, default=str)

    print(f"Exported {len(corrections)} corrections to {filepath}")
    return filepath


# ============================================================================
# CUSTOM SYMBOL FUNCTIONS (for template matching)
# ============================================================================

def save_custom_symbol(symbol_name: str, config: dict, templates_data: bytes):
    """
    Saves a custom symbol definition to the database.

    Args:
        symbol_name: Unique name for the symbol
        config: Symbol configuration as dict (will be stored as JSON)
        templates_data: Serialized numpy arrays (templates, contours, hu_moments) as bytes
    """
    config_json = json.dumps(config)

    print(f"Saving custom symbol '{symbol_name}' to database...")

    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            INSERT INTO custom_symbols (symbol_name, config_json, templates_data, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(symbol_name) DO UPDATE SET
                config_json = excluded.config_json,
                templates_data = excluded.templates_data,
                updated_at = excluded.updated_at
        """, (symbol_name, config_json, templates_data, datetime.now().isoformat()))

        conn.commit()
    finally:
        conn.close()

    print(f"Successfully saved custom symbol '{symbol_name}'.")


def get_all_custom_symbols() -> List[Dict]:
    """
    Retrieves all custom symbol definitions from the database.

    Returns:
        List of dicts with 'symbol_name', 'config', and 'templates_data'
    """
    # First check if table exists
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name='custom_symbols';
    """)
    table_exists = cursor.fetchone()

    if not table_exists:
        print("custom_symbols table does not exist yet.")
        conn.close()
        return []

    cursor.execute("""
        SELECT symbol_name, config_json, templates_data
        FROM custom_symbols
        ORDER BY symbol_name;
    """)
    results = cursor.fetchall()
    conn.close()

    symbols = []
    for row in results:
        config = json.loads(row[1]) if isinstance(row[1], str) else row[1]
        symbols.append({
            'symbol_name': row[0],
            'config': config,
            'templates_data': bytes(row[2]) if row[2] else None
        })

    print(f"Loaded {len(symbols)} custom symbols from database.")
    return symbols


def get_custom_symbol(symbol_name: str) -> Optional[Dict]:
    """
    Retrieves a single custom symbol definition from the database.

    Returns:
        Dict with 'symbol_name', 'config', and 'templates_data', or None if not found
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT symbol_name, config_json, templates_data
            FROM custom_symbols
            WHERE symbol_name = ?;
        """, (symbol_name,))
        row = cursor.fetchone()
        conn.close()

        if row:
            config = json.loads(row[1]) if isinstance(row[1], str) else row[1]
            return {
                'symbol_name': row[0],
                'config': config,
                'templates_data': bytes(row[2]) if row[2] else None
            }
        return None
    except Exception:
        return None


def delete_custom_symbol(symbol_name: str) -> bool:
    """
    Deletes a custom symbol from the database.

    Returns:
        True if deleted, False if not found
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()

        # Check if exists first
        cursor.execute("SELECT id FROM custom_symbols WHERE symbol_name = ?", (symbol_name,))
        exists = cursor.fetchone()

        if exists:
            cursor.execute("DELETE FROM custom_symbols WHERE symbol_name = ?", (symbol_name,))
            conn.commit()
            conn.close()
            print(f"Deleted custom symbol '{symbol_name}' from database.")
            return True
        else:
            conn.close()
            print(f"Custom symbol '{symbol_name}' not found in database.")
            return False
    except Exception as e:
        print(f"Error deleting custom symbol: {e}")
        return False


def is_db_available() -> bool:
    """Check if database connection is available."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        conn.close()
        return True
    except Exception:
        return False


# ============================================================================
# DATABASE UTILITIES
# ============================================================================

def get_db_path() -> str:
    """Return the current database file path."""
    return DB_PATH


def set_db_path(path: str):
    """Set a custom database file path."""
    global DB_PATH
    DB_PATH = path


def reset_database():
    """
    Remove and reinitialize the database.
    WARNING: This will delete all data!
    """
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
        print(f"Removed existing database: {DB_PATH}")
    init_db()


# Run initialization when module is imported (creates tables if they don't exist)
if __name__ == "__main__":
    print("=" * 60)
    print("SQLite DATABASE INITIALIZATION")
    print("=" * 60)
    init_db()
    print(f"\nDatabase location: {DB_PATH}")
    print("=" * 60)
