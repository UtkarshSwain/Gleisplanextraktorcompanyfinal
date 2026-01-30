"""
Simple database viewer for Gleisplanextraktor SQLite database.
Run this script to see what's stored in the database.
"""
import sqlite3
import os
from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "gleisplanextraktor.db"

def view_database():
    """Display all data in the database."""

    if not DB_PATH.exists():
        print(f"Database not found at: {DB_PATH}")
        print("No data has been saved yet.")
        return

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    print("=" * 70)
    print(f"DATABASE: {DB_PATH}")
    print(f"Size: {os.path.getsize(DB_PATH) / 1024:.1f} KB")
    print("=" * 70)

    # 1. Show all layouts
    print("\n[1] SAVED LAYOUTS (track_layouts)")
    print("-" * 50)
    cursor.execute("SELECT * FROM track_layouts ORDER BY id")
    layouts = cursor.fetchall()
    if layouts:
        for row in layouts:
            print(f"  ID: {row['id']}, Name: {row['layout_name']}")
    else:
        print("  (No layouts saved)")

    # 2. Show workspaces
    print("\n[2] WORKSPACES (saved detection data)")
    print("-" * 50)
    cursor.execute("""
        SELECT t.layout_name, w.last_modified,
               LENGTH(w.edited_data_json) as data_size,
               CASE WHEN w.track_skeleton IS NOT NULL THEN 'Yes' ELSE 'No' END as has_skeleton,
               CASE WHEN w.image_dimensions IS NOT NULL THEN 'Yes' ELSE 'No' END as has_dimensions
        FROM workspaces w
        JOIN track_layouts t ON w.layout_id = t.id
        ORDER BY w.last_modified DESC
    """)
    workspaces = cursor.fetchall()
    if workspaces:
        for row in workspaces:
            print(f"  Layout: {row['layout_name']}")
            print(f"    Last Modified: {row['last_modified']}")
            print(f"    Data Size: {row['data_size'] / 1024:.1f} KB")
            print(f"    Has Track Skeleton: {row['has_skeleton']}")
            print(f"    Has Image Dimensions: {row['has_dimensions']}")
            print()
    else:
        print("  (No workspaces saved)")

    # 3. Show custom symbols
    print("\n[3] CUSTOM SYMBOLS (template matching)")
    print("-" * 50)
    cursor.execute("""
        SELECT symbol_name, created_at, updated_at,
               LENGTH(templates_data) as template_size
        FROM custom_symbols
        ORDER BY symbol_name
    """)
    symbols = cursor.fetchall()
    if symbols:
        for row in symbols:
            size = row['template_size'] or 0
            print(f"  Symbol: {row['symbol_name']}")
            print(f"    Created: {row['created_at']}")
            print(f"    Updated: {row['updated_at']}")
            print(f"    Template Size: {size / 1024:.1f} KB")
            print()
    else:
        print("  (No custom symbols saved)")

    # 4. Show validation summary
    print("\n[4] VALIDATION LOG (summary)")
    print("-" * 50)
    cursor.execute("""
        SELECT t.layout_name, v.severity, COUNT(*) as count
        FROM validation_log v
        JOIN track_layouts t ON v.layout_id = t.id
        GROUP BY t.layout_name, v.severity
        ORDER BY t.layout_name, v.severity
    """)
    validations = cursor.fetchall()
    if validations:
        current_layout = None
        for row in validations:
            if row['layout_name'] != current_layout:
                current_layout = row['layout_name']
                print(f"  Layout: {current_layout}")
            print(f"    {row['severity']}: {row['count']} issues")
    else:
        print("  (No validation results saved)")

    # 5. Show correction statistics
    print("\n[5] MANUAL CORRECTIONS (summary)")
    print("-" * 50)
    cursor.execute("""
        SELECT t.layout_name, COUNT(*) as correction_count,
               COUNT(DISTINCT mc.row_id) as rows_affected
        FROM manual_corrections mc
        JOIN track_layouts t ON mc.layout_id = t.id
        GROUP BY t.layout_name
        ORDER BY correction_count DESC
    """)
    corrections = cursor.fetchall()
    if corrections:
        for row in corrections:
            print(f"  Layout: {row['layout_name']}")
            print(f"    Total Corrections: {row['correction_count']}")
            print(f"    Rows Affected: {row['rows_affected']}")
            print()
    else:
        print("  (No manual corrections logged)")

    # 6. Show quality metrics
    print("\n[6] QUALITY METRICS")
    print("-" * 50)
    cursor.execute("""
        SELECT t.layout_name, q.metric_name, q.metric_value, q.computed_at
        FROM quality_metrics q
        JOIN track_layouts t ON q.layout_id = t.id
        ORDER BY t.layout_name, q.metric_name
    """)
    metrics = cursor.fetchall()
    if metrics:
        current_layout = None
        for row in metrics:
            if row['layout_name'] != current_layout:
                current_layout = row['layout_name']
                print(f"  Layout: {current_layout}")
            value = f"{row['metric_value']:.2f}" if row['metric_value'] else "N/A"
            print(f"    {row['metric_name']}: {value}")
    else:
        print("  (No quality metrics saved)")

    print("\n" + "=" * 70)
    conn.close()


def delete_layout(layout_name: str):
    """Delete a specific layout and all associated data."""
    if not DB_PATH.exists():
        print("Database not found.")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Get layout ID
    cursor.execute("SELECT id FROM track_layouts WHERE layout_name = ?", (layout_name,))
    result = cursor.fetchone()

    if not result:
        print(f"Layout '{layout_name}' not found.")
        conn.close()
        return

    # Delete (CASCADE will handle related tables)
    cursor.execute("DELETE FROM track_layouts WHERE layout_name = ?", (layout_name,))
    conn.commit()
    conn.close()

    print(f"Deleted layout '{layout_name}' and all associated data.")


def clear_all():
    """Clear all data from the database."""
    if not DB_PATH.exists():
        print("Database not found.")
        return

    confirm = input("Are you sure you want to delete ALL data? (yes/no): ")
    if confirm.lower() != 'yes':
        print("Cancelled.")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("DELETE FROM track_layouts")  # CASCADE deletes everything
    conn.commit()
    conn.close()

    print("All data cleared.")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        command = sys.argv[1]

        if command == "delete" and len(sys.argv) > 2:
            delete_layout(sys.argv[2])
        elif command == "clear":
            clear_all()
        else:
            print("Usage:")
            print("  python db_viewer.py          - View all data")
            print("  python db_viewer.py delete <layout_name>  - Delete a layout")
            print("  python db_viewer.py clear    - Clear all data")
    else:
        view_database()
