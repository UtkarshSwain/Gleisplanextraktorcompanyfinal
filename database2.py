import psycopg2
import psycopg2.extras # For getting data as dictionaries
import json
import os
import numpy as np
import base64
import io
import zlib
from contextlib import contextmanager
from typing import Optional, Tuple, List, Dict
import psutil  # For memory monitoring

# Load sensitive info from environment variables.
DB_NAME = "track_layouts_db"
DB_USER = "swain.utkarsh@siemens.com"
DB_PASS = os.environ.get("DB_PASSWORD")
DB_HOST = "172.31.84.87"
DB_PORT = "5432"

def get_memory_usage():
    """Get current memory usage in MB"""
    process = psutil.Process(os.getpid())
    mem_mb = process.memory_info().rss / 1024 / 1024
    return mem_mb

def log_memory(prefix: str = ""):
    """Print current memory usage"""
    mem_mb = get_memory_usage()
    print(f"[MEM] {prefix}: {mem_mb:.1f} MB")

def get_connection():
    """Establishes a connection to the database."""
    if DB_PASS is None:
        raise ValueError("DB_PASSWORD environment variable is not set.")
        
    return psycopg2.connect(
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASS,
        host=DB_HOST,
        port=DB_PORT
    )

@contextmanager
def db_cursor(commit=False):
    """A helper to manage database connections and cursors safely."""
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            yield cursor
            if commit:
                conn.commit()
    finally:
        conn.close()

def init_db():
    """
    Initializes the database by creating tables if they don't exist.
    Also adds track_skeleton column to existing workspaces table.
    """
    sql_create_layouts_table = """
    CREATE TABLE IF NOT EXISTS track_layouts (
        id SERIAL PRIMARY KEY,
        layout_name TEXT UNIQUE NOT NULL
    );
    """
    
    sql_create_workspaces_table = """
    CREATE TABLE IF NOT EXISTS workspaces (
        id SERIAL PRIMARY KEY,
        layout_id INTEGER UNIQUE NOT NULL REFERENCES track_layouts(id) ON DELETE CASCADE,
        edited_data_json JSONB NOT NULL,
        track_skeleton TEXT,
        last_modified TIMESTAMPTZ DEFAULT NOW()
    );
    """
    
    sql_add_track_skeleton = """
    DO $$ 
    BEGIN
        BEGIN
            ALTER TABLE workspaces ADD COLUMN track_skeleton TEXT;
        EXCEPTION
            WHEN duplicate_column THEN 
                RAISE NOTICE 'column track_skeleton already exists in workspaces.';
        END;
    END $$;
    """
    
    try:
        with db_cursor(commit=True) as cursor:
            print("Initializing database tables...")
            cursor.execute(sql_create_layouts_table)
            cursor.execute(sql_create_workspaces_table)
            cursor.execute(sql_add_track_skeleton)
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
    
    Typical compression: 10MB → 50KB (200x smaller!)
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
        print(f"  ✓ Track skeleton compressed: {original_size/1024/1024:.1f}MB → {compressed_size/1024:.1f}KB ({ratio:.0f}x)")
        
        return b64_str
        
    except Exception as e:
        print(f"  ⚠️ Compression failed: {e}")
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
        print(f"  ✓ Track skeleton decompressed: {skeleton.shape}")
        
        return skeleton
        
    except Exception as e:
        print(f"  ⚠️ Decompression failed: {e}")
        return None

def get_workspace_data(layout_name: str) -> Optional[Tuple[List[Dict], Optional[np.ndarray]]]:
    """
    Retrieves the saved workspace JSON data and track skeleton for a given layout name.
    
    Returns:
        Tuple of (data_list, track_skeleton) or None if not found
    """
    log_memory(f"Loading workspace: {layout_name}")
    print(f"Checking database for workspace: {layout_name}")
    
    sql_query = """
    SELECT w.edited_data_json, w.track_skeleton
    FROM workspaces w
    JOIN track_layouts t ON w.layout_id = t.id
    WHERE t.layout_name = %s;
    """
    
    with db_cursor() as cursor:
        cursor.execute(sql_query, (layout_name,))
        result = cursor.fetchone()
        
        if result:
            print(f"Found saved data for {layout_name}.")
            
            # Get the JSON data
            workspace_data = result['edited_data_json']
            
            # Decompress track skeleton if present
            track_skeleton = None
            track_skeleton_compressed = result.get('track_skeleton')
            
            if track_skeleton_compressed:
                try:
                    track_skeleton = decompress_track_skeleton(track_skeleton_compressed)
                except Exception as e:
                    print(f"  ⚠️ Could not load track skeleton: {e}")
                    track_skeleton = None
            else:
                print(f"  ℹ️ No track skeleton saved for this layout")
            
            log_memory("Workspace loaded")
            return workspace_data, track_skeleton
        else:
            print(f"No saved data found for {layout_name}.")
            return None

def save_workspace_data(layout_name: str, workspace_data: List[Dict], 
                       track_skeleton: Optional[np.ndarray] = None):
    """
    Saves (Inserts or Updates) the workspace data and track skeleton for a given layout name.
    
    Args:
        layout_name: Unique identifier for the layout
        workspace_data: List of detection dictionaries
        track_skeleton: Optional track centerline mask (numpy array)
    """
    log_memory(f"Saving workspace: {layout_name}")
    
    sql_insert_layout = """
    INSERT INTO track_layouts (layout_name)
    VALUES (%s)
    ON CONFLICT (layout_name) DO NOTHING;
    """
    
    sql_get_layout_id = "SELECT id FROM track_layouts WHERE layout_name = %s;"
    
    sql_upsert_workspace = """
    INSERT INTO workspaces (layout_id, edited_data_json, track_skeleton, last_modified)
    VALUES (%s, %s, %s, NOW())
    ON CONFLICT (layout_id)
    DO UPDATE SET
        edited_data_json = EXCLUDED.edited_data_json,
        track_skeleton = EXCLUDED.track_skeleton,
        last_modified = NOW();
    """
    
    # Convert workspace data to JSON string
    data_as_json_string = json.dumps(workspace_data)
    
    # Compress track skeleton if present
    track_skeleton_compressed = None
    if track_skeleton is not None:
        track_skeleton_compressed = compress_track_skeleton(track_skeleton)

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
        
        # Upsert workspace data + track skeleton
        cursor.execute(sql_upsert_workspace, (layout_id, data_as_json_string, track_skeleton_compressed))
    
    log_memory("Workspace saved")
    print(f"Successfully saved workspace for {layout_name} (track: {track_skeleton is not None}).")