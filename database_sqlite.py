"""
SQLite database module for Gleisplanextraktor.
Provides local file-based storage with no external dependencies.

Features:
- Local SQLite database file
- Memory logging utilities for debugging
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
from pathlib import Path

# Optional psutil for memory monitoring
try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False


# ============================================================================
# MEMORY LOGGING UTILITIES
# ============================================================================

def get_memory_usage() -> float:
    """Get current memory usage in MB."""
    if HAS_PSUTIL:
        process = psutil.Process(os.getpid())
        mem_mb = process.memory_info().rss / 1024 / 1024
        return mem_mb
    return 0.0


def log_memory(prefix: str = ""):
    """Print current memory usage with optional prefix."""
    if HAS_PSUTIL:
        mem_mb = get_memory_usage()
        print(f"[MEM] {prefix}: {mem_mb:.1f} MB")


# ============================================================================
# DATABASE CONFIGURATION
# ============================================================================

# Database file location - in user's app data or project directory
def get_db_path() -> str:
    """Get the path to the SQLite database file."""
    # Store in the project directory for simplicity
    db_dir = Path(__file__).parent / "data"
    db_dir.mkdir(exist_ok=True)
    return str(db_dir / "gleisplanextraktor.db")

DB_PATH = get_db_path()


def dict_factory(cursor, row):
    """Convert SQLite rows to dictionaries."""
    fields = [column[0] for column in cursor.description]
    return {key: value for key, value in zip(fields, row)}


def get_connection():
    """Establishes a connection to the SQLite database."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = dict_factory
    # Enable foreign keys
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def db_cursor(commit=False):
    """A helper to manage database connections and cursors safely."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
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
        with db_cursor(commit=True) as cursor:
            print(f"Initializing SQLite database at {DB_PATH}...")
            cursor.execute(sql_create_layouts_table)
            cursor.execute(sql_create_workspaces_table)
            cursor.execute(sql_create_validation_log)
            cursor.execute(sql_create_quality_metrics)
            cursor.execute(sql_create_manual_corrections)
            cursor.execute(sql_create_custom_symbols)

            # Create indexes
            for index_sql in sql_create_indexes:
                cursor.execute(index_sql)

            # Migration: Add new columns if they don't exist (for existing databases)
            cursor.execute("PRAGMA table_info(workspaces)")
            columns = {row['name'] for row in cursor.fetchall()}

            if 'learned_patterns_json' not in columns:
                try:
                    cursor.execute("ALTER TABLE workspaces ADD COLUMN learned_patterns_json TEXT;")
                    print("  Added learned_patterns_json column")
                except sqlite3.OperationalError:
                    pass  # Column already exists

            if 'uncertain_detections_json' not in columns:
                try:
                    cursor.execute("ALTER TABLE workspaces ADD COLUMN uncertain_detections_json TEXT;")
                    print("  Added uncertain_detections_json column")
                except sqlite3.OperationalError:
                    pass  # Column already exists

            print("Database tables are ready.")
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

        print(f"  Track skeleton compressed: {original_size/1024/1024:.1f}MB -> {compressed_size/1024:.1f}KB ({ratio:.0f}x)")

        return b64_str

    except Exception as e:
        print(f"  Compression failed: {e}")
        return None


def decompress_track_skeleton(compressed_str: str) -> Optional[np.ndarray]:
    """
    Decompress track skeleton from compressed sparse format.
    """
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

        print(f"  Track skeleton decompressed: {skeleton.shape}")

        return skeleton

    except Exception as e:
        print(f"  Decompression failed: {e}")
        return None


def get_workspace_data(layout_name: str) -> Optional[Tuple[List[Dict], Optional[np.ndarray], Optional[Dict], Optional[Dict], Optional[List]]]:
    """
    Retrieves the saved workspace JSON data, track skeleton, image dimensions, and metadata.

    Returns:
        Tuple of (data_list, track_skeleton, image_dimensions, learned_patterns, uncertain_detections) or None if not found
    """
    print(f"Checking database for workspace: {layout_name}")

    sql_query = """
    SELECT w.edited_data_json, w.track_skeleton, w.image_dimensions,
           w.learned_patterns_json, w.uncertain_detections_json
    FROM workspaces w
    JOIN track_layouts t ON w.layout_id = t.id
    WHERE t.layout_name = ?;
    """

    with db_cursor() as cursor:
        cursor.execute(sql_query, (layout_name,))
        result = cursor.fetchone()

        if result:
            print(f"Found saved data for {layout_name}.")

            # Parse the JSON data
            workspace_data = json.loads(result['edited_data_json'])

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
                    dimensions_dict = json.loads(image_dimensions_json)
                    image_dimensions = {int(k): v for k, v in dimensions_dict.items()}
                    print(f"  Loaded image dimensions: {image_dimensions}")
                except Exception as e:
                    print(f"  Could not parse image dimensions: {e}")
                    image_dimensions = None
            else:
                print(f"  No image dimensions saved for this layout")

            # Parse learned_patterns (OCR learning data)
            learned_patterns = None
            learned_patterns_json = result.get('learned_patterns_json')
            if learned_patterns_json:
                try:
                    learned_patterns = json.loads(learned_patterns_json)
                    print(f"  Loaded {len(learned_patterns) if learned_patterns else 0} learned patterns")
                except Exception as e:
                    print(f"  Could not parse learned_patterns: {e}")
                    learned_patterns = None

            # Parse uncertain_detections (low-confidence items)
            uncertain_detections = None
            uncertain_detections_json = result.get('uncertain_detections_json')
            if uncertain_detections_json:
                try:
                    uncertain_detections = json.loads(uncertain_detections_json)
                    print(f"  Loaded {len(uncertain_detections) if uncertain_detections else 0} uncertain detections")
                except Exception as e:
                    print(f"  Could not parse uncertain_detections: {e}")
                    uncertain_detections = None

            return workspace_data, track_skeleton, image_dimensions, learned_patterns, uncertain_detections
        else:
            print(f"No saved data found for {layout_name}.")
            return None


def save_workspace_data(layout_name: str, workspace_data: List[Dict],
                       track_skeleton: Optional[np.ndarray] = None,
                       image_dimensions: Optional[dict] = None,
                       learned_patterns: Optional[dict] = None,
                       uncertain_detections: Optional[list] = None):
    """
    Saves (Inserts or Updates) the workspace data, track skeleton, image dimensions,
    and workspace-level metadata.

    Args:
        layout_name: Unique identifier for the layout
        workspace_data: List of detection dictionaries
        track_skeleton: Optional track centerline mask (numpy array)
        image_dimensions: Optional dict of {page_num: {'width': w, 'height': h}}
        learned_patterns: Optional dict of OCR learning patterns
        uncertain_detections: Optional list of low-confidence detections
    """
    sql_insert_layout = """
    INSERT OR IGNORE INTO track_layouts (layout_name)
    VALUES (?);
    """

    sql_get_layout_id = "SELECT id FROM track_layouts WHERE layout_name = ?;"

    sql_upsert_workspace = """
    INSERT INTO workspaces (layout_id, edited_data_json, track_skeleton, image_dimensions,
                           learned_patterns_json, uncertain_detections_json, last_modified)
    VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
    ON CONFLICT (layout_id)
    DO UPDATE SET
        edited_data_json = excluded.edited_data_json,
        track_skeleton = excluded.track_skeleton,
        image_dimensions = excluded.image_dimensions,
        learned_patterns_json = excluded.learned_patterns_json,
        uncertain_detections_json = excluded.uncertain_detections_json,
        last_modified = CURRENT_TIMESTAMP;
    """

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

    # Convert image dimensions to JSON
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

    # Serialize learned_patterns (OCR learning data)
    learned_patterns_json = None
    if learned_patterns:
        try:
            learned_patterns_json = json.dumps(learned_patterns, cls=NumpyEncoder)
        except Exception as e:
            print(f"Failed to serialize learned_patterns: {e}")
            learned_patterns_json = None

    # Serialize uncertain_detections (low-confidence items)
    uncertain_detections_json = None
    if uncertain_detections:
        try:
            uncertain_detections_json = json.dumps(uncertain_detections, cls=NumpyEncoder)
        except Exception as e:
            print(f"Failed to serialize uncertain_detections: {e}")
            uncertain_detections_json = None

    print(f"Saving workspace for {layout_name}...")

    with db_cursor(commit=True) as cursor:
        # Ensure layout exists
        cursor.execute(sql_insert_layout, (layout_name,))

        # Get layout ID
        cursor.execute(sql_get_layout_id, (layout_name,))
        layout_id_result = cursor.fetchone()
        if not layout_id_result:
            raise Exception(f"Could not create or find layout_id for {layout_name}")
        layout_id = layout_id_result['id']

        # Upsert workspace data + track skeleton + image dimensions + metadata
        cursor.execute(sql_upsert_workspace, (
            layout_id,
            data_as_json_string,
            track_skeleton_compressed,
            image_dimensions_json,
            learned_patterns_json,
            uncertain_detections_json
        ))

    print(f"Saved workspace for {layout_name} (track: {track_skeleton is not None}, dims: {image_dimensions is not None}, patterns: {learned_patterns is not None}).")


def delete_workspace_data(layout_name: str) -> bool:
    """
    Delete workspace data for a specific layout.
    """
    sql_get_layout_id = "SELECT id FROM track_layouts WHERE layout_name = ?;"
    sql_delete_workspace = "DELETE FROM workspaces WHERE layout_id = ?;"

    try:
        with db_cursor(commit=True) as cursor:
            cursor.execute(sql_get_layout_id, (layout_name,))
            layout_id_result = cursor.fetchone()

            if not layout_id_result:
                print(f"No layout found with name: {layout_name}")
                return False

            layout_id = layout_id_result['id']
            cursor.execute(sql_delete_workspace, (layout_id,))

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
    """
    sql_get_layout_id = "SELECT id FROM track_layouts WHERE layout_name = ?;"
    sql_clear_old = "DELETE FROM validation_log WHERE layout_id = ?;"

    sql_insert_validation = """
    INSERT INTO validation_log (layout_id, validation_type, severity, message, row_id, details)
    VALUES (?, ?, ?, ?, ?, ?);
    """

    with db_cursor(commit=True) as cursor:
        cursor.execute(sql_get_layout_id, (layout_name,))
        layout_id_result = cursor.fetchone()

        if not layout_id_result:
            print(f"Layout {layout_name} not found in database")
            return

        layout_id = layout_id_result['id']

        # Clear old results
        cursor.execute(sql_clear_old, (layout_id,))

        # Insert new results
        for result in validation_results:
            validation_type = result.message.split(':')[0] if ':' in result.message else 'general'

            cursor.execute(sql_insert_validation, (
                layout_id,
                validation_type,
                result.severity,
                result.message,
                result.row_id,
                json.dumps(result.details) if result.details else None
            ))

        print(f"Saved {len(validation_results)} validation results for {layout_name}")


def get_validation_results(layout_name: str) -> List[Dict]:
    """
    Retrieve validation results for a layout.
    """
    sql_query = """
    SELECT v.validation_type, v.severity, v.message, v.row_id, v.details, v.created_at
    FROM validation_log v
    JOIN track_layouts t ON v.layout_id = t.id
    WHERE t.layout_name = ?
    ORDER BY
        CASE v.severity
            WHEN 'ERROR' THEN 1
            WHEN 'WARNING' THEN 2
            WHEN 'INFO' THEN 3
        END,
        v.created_at DESC;
    """

    with db_cursor() as cursor:
        cursor.execute(sql_query, (layout_name,))
        results = cursor.fetchall()

        # Parse JSON details
        for r in results:
            if r.get('details'):
                r['details'] = json.loads(r['details'])

        return results


def save_quality_metrics(layout_name: str, metrics: Dict):
    """
    Save data quality metrics to database.
    """
    sql_get_layout_id = "SELECT id FROM track_layouts WHERE layout_name = ?;"

    sql_insert_metric = """
    INSERT INTO quality_metrics (layout_id, metric_name, metric_value, metric_data)
    VALUES (?, ?, ?, ?);
    """

    with db_cursor(commit=True) as cursor:
        cursor.execute(sql_get_layout_id, (layout_name,))
        layout_id_result = cursor.fetchone()

        if not layout_id_result:
            print(f"Layout {layout_name} not found in database")
            return

        layout_id = layout_id_result['id']

        # Insert metrics
        for metric_name, metric_info in metrics.items():
            if isinstance(metric_info, dict):
                metric_value = metric_info.get('value')
                metric_data = json.dumps(metric_info.get('data', {}))
            else:
                metric_value = float(metric_info) if isinstance(metric_info, (int, float)) else None
                metric_data = None

            cursor.execute(sql_insert_metric, (
                layout_id,
                metric_name,
                metric_value,
                metric_data
            ))

        print(f"Saved {len(metrics)} quality metrics for {layout_name}")


def get_quality_metrics(layout_name: str, metric_name: Optional[str] = None) -> List[Dict]:
    """
    Retrieve quality metrics for a layout.
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

        # Parse JSON metric_data
        for r in results:
            if r.get('metric_data'):
                r['metric_data'] = json.loads(r['metric_data'])

        return results


def get_validation_summary(layout_name: str) -> Dict:
    """
    Get a summary of validation results for a layout.
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
    """
    sql_get_layout_id = "SELECT id FROM track_layouts WHERE layout_name = ?;"

    sql_insert_correction = """
    INSERT INTO manual_corrections
        (layout_id, row_id, column_name, old_value, new_value, correction_type, corrected_by, correction_reason)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?);
    """

    try:
        with db_cursor(commit=True) as cursor:
            cursor.execute(sql_get_layout_id, (layout_name,))
            layout_id_result = cursor.fetchone()

            if not layout_id_result:
                print(f"Layout {layout_name} not found in database")
                return

            layout_id = layout_id_result['id']

            # Convert values to strings for storage
            old_value_str = str(old_value) if old_value is not None else None
            new_value_str = str(new_value) if new_value is not None else None

            cursor.execute(sql_insert_correction, (
                layout_id,
                row_id,
                column_name,
                old_value_str,
                new_value_str,
                correction_type,
                corrected_by,
                correction_reason
            ))

            print(f"Logged correction: Row {row_id}, {column_name}: {old_value} -> {new_value}")

    except Exception as e:
        print(f"Error logging manual correction: {e}")


def get_correction_history(layout_name: str, row_id: Optional[int] = None) -> List[Dict]:
    """
    Retrieve correction history for a layout.
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
        return cursor.fetchall()


def get_correction_statistics(layout_name: Optional[str] = None) -> List[Dict]:
    """
    Get statistics about corrections.
    """
    if layout_name:
        sql_query = """
        SELECT
            t.layout_name,
            mc.column_name,
            COUNT(*) as correction_count,
            COUNT(DISTINCT mc.row_id) as affected_rows,
            MIN(mc.created_at) as first_correction,
            MAX(mc.created_at) as last_correction
        FROM manual_corrections mc
        JOIN track_layouts t ON mc.layout_id = t.id
        WHERE t.layout_name = ?
        GROUP BY t.layout_name, mc.column_name
        ORDER BY correction_count DESC;
        """
        params = (layout_name,)
    else:
        sql_query = """
        SELECT
            t.layout_name,
            mc.column_name,
            COUNT(*) as correction_count,
            COUNT(DISTINCT mc.row_id) as affected_rows,
            MIN(mc.created_at) as first_correction,
            MAX(mc.created_at) as last_correction
        FROM manual_corrections mc
        JOIN track_layouts t ON mc.layout_id = t.id
        GROUP BY t.layout_name, mc.column_name
        ORDER BY correction_count DESC;
        """
        params = ()

    with db_cursor() as cursor:
        cursor.execute(sql_query, params)
        return cursor.fetchall()


def get_most_corrected_fields(layout_name: str, limit: int = 10) -> List[Dict]:
    """
    Get the most frequently corrected fields for a layout.
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
        return cursor.fetchall()


def export_corrections_for_retraining(layout_name: str, output_dir: str):
    """
    Export correction data in a format suitable for model retraining.
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
    """
    sql_upsert = """
    INSERT INTO custom_symbols (symbol_name, config_json, templates_data, updated_at)
    VALUES (?, ?, ?, CURRENT_TIMESTAMP)
    ON CONFLICT (symbol_name)
    DO UPDATE SET
        config_json = excluded.config_json,
        templates_data = excluded.templates_data,
        updated_at = CURRENT_TIMESTAMP;
    """

    config_json = json.dumps(config)

    print(f"Saving custom symbol '{symbol_name}' to database...")
    with db_cursor(commit=True) as cursor:
        cursor.execute(sql_upsert, (symbol_name, config_json, templates_data))
    print(f"Successfully saved custom symbol '{symbol_name}'.")


def get_all_custom_symbols() -> List[Dict]:
    """
    Retrieves all custom symbol definitions from the database.
    """
    # Check if table exists
    sql_check_table = """
    SELECT name FROM sqlite_master
    WHERE type='table' AND name='custom_symbols';
    """

    sql_query = """
    SELECT symbol_name, config_json, templates_data
    FROM custom_symbols
    ORDER BY symbol_name;
    """

    with db_cursor() as cursor:
        cursor.execute(sql_check_table)
        table_exists = cursor.fetchone()

        if not table_exists:
            print("custom_symbols table does not exist yet.")
            return []

        cursor.execute(sql_query)
        results = cursor.fetchall()

        symbols = []
        for row in results:
            symbols.append({
                'symbol_name': row['symbol_name'],
                'config': json.loads(row['config_json']) if row['config_json'] else {},
                'templates_data': row['templates_data']
            })

        print(f"Loaded {len(symbols)} custom symbols from database.")
        return symbols


def get_custom_symbol(symbol_name: str) -> Optional[Dict]:
    """
    Retrieves a single custom symbol definition from the database.
    """
    sql_query = """
    SELECT symbol_name, config_json, templates_data
    FROM custom_symbols
    WHERE symbol_name = ?;
    """

    try:
        with db_cursor() as cursor:
            cursor.execute(sql_query, (symbol_name,))
            row = cursor.fetchone()

            if row:
                return {
                    'symbol_name': row['symbol_name'],
                    'config': json.loads(row['config_json']) if row['config_json'] else {},
                    'templates_data': row['templates_data']
                }
            return None
    except Exception:
        return None


def delete_custom_symbol(symbol_name: str) -> bool:
    """
    Deletes a custom symbol from the database AND local files.
    """
    sql_delete = "DELETE FROM custom_symbols WHERE symbol_name = ?;"
    sql_check = "SELECT changes();"

    deleted_from_db = False
    deleted_from_files = False

    # Delete from database
    try:
        with db_cursor(commit=True) as cursor:
            cursor.execute(sql_delete, (symbol_name,))
            cursor.execute(sql_check)
            result = cursor.fetchone()

            if result and result.get('changes()', 0) > 0:
                print(f"Deleted custom symbol '{symbol_name}' from database.")
                deleted_from_db = True
            else:
                print(f"Custom symbol '{symbol_name}' not found in database.")
    except Exception as e:
        print(f"Error deleting custom symbol from database: {e}")

    # Delete from local JSON file
    try:
        config_path = Path(__file__).parent / "custom_symbols.json"
        if config_path.exists():
            with open(config_path, 'r') as f:
                symbols_data = json.load(f)

            if symbol_name in symbols_data:
                del symbols_data[symbol_name]
                with open(config_path, 'w') as f:
                    json.dump(symbols_data, f, indent=2)
                print(f"Deleted '{symbol_name}' from custom_symbols.json")
                deleted_from_files = True
    except Exception as e:
        print(f"Error deleting from JSON file: {e}")

    # Delete template directory
    try:
        import shutil
        templates_dir = Path(__file__).parent / "custom_symbol_templates" / symbol_name
        if templates_dir.exists():
            shutil.rmtree(templates_dir)
            print(f"Deleted template directory for '{symbol_name}'")
            deleted_from_files = True
    except Exception as e:
        print(f"Error deleting template directory: {e}")

    return deleted_from_db or deleted_from_files


def is_db_available() -> bool:
    """Check if database connection is available."""
    try:
        with db_cursor() as cursor:
            cursor.execute("SELECT 1")
            return True
    except Exception:
        return False


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


# Initialize database when module is first imported
if __name__ == "__main__":
    print("=" * 60)
    print("SQLite DATABASE INITIALIZATION")
    print("=" * 60)
    init_db()
    print("=" * 60)
