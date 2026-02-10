"""
PDF Comparison module for track layout versioning.

This module provides functionality for comparing different versions of
railway track layout PDFs to detect changes in symbols and coordinates.

Main components:
    comparison_engine: LayoutComparisonEngine, ElementChange, ChangeType, ChangeSeverity
    dialogs: HelpDialog, GraphicsWindow, TreeWindow, PDFComparisonDialog

Usage:
    from pdfcomparison.comparison_engine import LayoutComparisonEngine
    from pdfcomparison.dialogs import HelpDialog
"""
# Note: Explicit imports avoided to prevent circular import issues
# with ui modules. Use direct imports from submodules instead.
