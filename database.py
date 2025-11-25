import psycopg2
import psycopg2.extras # For getting data as dictionaries
import json
import os
from contextlib import contextmanager

# Load sensitive info from environment variables.
# This is better than hard-coding them.
# Set them in your terminal: export DB_PASSWORD="your_strong_password_here"
DB_NAME = "track_layouts_db"
DB_USER = "swain.utkarsh@siemens.com"
DB_PASS = os.environ.get("DB_PASSWORD") # Get password from environment
DB_HOST = "172.31.84.87"
DB_PORT = "5432"

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
    # Use RealDictCursor to get results as dictionaries
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
    Call this one time when your main application starts.
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
        last_modified TIMESTAMPTZ DEFAULT NOW()
    );
    """
    
    try:
        with db_cursor(commit=True) as cursor:
            print("Initializing database tables...")
            cursor.execute(sql_create_layouts_table)
            cursor.execute(sql_create_workspaces_table)
            print("Database tables are ready.")
    except Exception as e:
        print(f"Error initializing database: {e}")
        raise

def get_workspace_data(layout_name):
    """
    Retrieves the saved workspace JSON data for a given layout name.
    Returns the data if found, otherwise returns None.
    """
    print(f"Checking database for workspace: {layout_name}")
    sql_query = """
    SELECT w.edited_data_json
    FROM workspaces w
    JOIN track_layouts t ON w.layout_id = t.id
    WHERE t.layout_name = %s;
    """
    with db_cursor() as cursor:
        cursor.execute(sql_query, (layout_name,))
        result = cursor.fetchone()
        
        if result:
            print(f"Found saved data for {layout_name}.")
            return result['edited_data_json']  # This is already a dict/list
        else:
            print(f"No saved data found for {layout_name}.")
            return None

def save_workspace_data(layout_name, workspace_data):
    """
    Saves (Inserts or Updates) the workspace data for a given layout name.
    """
    # 1. Ensure the layout_name exists in the 'track_layouts' table
    sql_insert_layout = """
    INSERT INTO track_layouts (layout_name)
    VALUES (%s)
    ON CONFLICT (layout_name) DO NOTHING;
    """
    
    # 2. Get the ID for that layout_name
    sql_get_layout_id = "SELECT id FROM track_layouts WHERE layout_name = %s;"
    
    # 3. Insert or Update the workspace data
    #    We use ON CONFLICT to do an "UPSERT" (Update if it exists, Insert if not)
    sql_upsert_workspace = """
    INSERT INTO workspaces (layout_id, edited_data_json, last_modified)
    VALUES (%s, %s, NOW())
    ON CONFLICT (layout_id)
    DO UPDATE SET
        edited_data_json = EXCLUDED.edited_data_json,
        last_modified = NOW();
    """
    
    # Convert your data to a JSON string
    data_as_json_string = json.dumps(workspace_data)

    print(f"Saving workspace for {layout_name}...")
    with db_cursor(commit=True) as cursor:
        # Step 1
        cursor.execute(sql_insert_layout, (layout_name,))
        
        # Step 2
        cursor.execute(sql_get_layout_id, (layout_name,))
        layout_id_result = cursor.fetchone()
        if not layout_id_result:
            raise Exception(f"Could not create or find layout_id for {layout_name}")
        layout_id = layout_id_result['id']
        
        # Step 3
        cursor.execute(sql_upsert_workspace, (layout_id, data_as_json_string))
    
    print(f"Successfully saved workspace for {layout_name}.")