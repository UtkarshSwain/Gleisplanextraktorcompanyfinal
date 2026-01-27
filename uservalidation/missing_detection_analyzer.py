# uservalidation/missing_detection_analyzer.py
"""
Missing Detection Analyzer - Find areas where YOLO likely missed objects

Uses spatial analysis to find:
1. Gaps in coordinate sequences
2. Isolated text regions without detections
3. Areas with expected patterns but no detections
"""

import pandas as pd
import numpy as np
from typing import List, Tuple, Dict
from dataclasses import dataclass

@dataclass
class MissingDetectionRegion:
    """Represents a region where a detection might be missing"""
    region_type: str  # 'coordinate_gap', 'isolated_text', 'pattern_break'
    expected_class: str  # What class we expect to find
    bbox: Tuple[float, float, float, float]  # (x1, y1, x2, y2)
    center: Tuple[float, float]  # (xc, yc)
    confidence: float  # How confident we are something is missing (0-1)
    reason: str  # Human-readable explanation
    page: int
    context: Dict  # Additional context data

class MissingDetectionAnalyzer:
    """
    Analyze DataFrame to find potential missing detections.
    """
    
    def __init__(self, df: pd.DataFrame):
        self.df = df
        self.missing_regions: List[MissingDetectionRegion] = []
    
    def analyze_all(self) -> List[MissingDetectionRegion]:
        """Run all missing detection checks"""
        self.missing_regions = []
        
        # Check for coordinate gaps
        self.missing_regions.extend(self._find_coordinate_gaps())
        
        # Check for signal/GKS without coordinates
        self.missing_regions.extend(self._find_orphaned_objects())
        
        # Check for pattern breaks (e.g., signal-coord-signal-coord-signal-[MISSING COORD])
        self.missing_regions.extend(self._find_pattern_breaks())
        
        return self.missing_regions
    
    def _find_coordinate_gaps(self, max_gap: float = 800) -> List[MissingDetectionRegion]:
        """
        Find large gaps in coordinate sequences.
        If coordinates are at 10.5, 11.2, 13.8, there's likely a missing one at ~12.5
        """
        regions = []
        
        coords = self.df[self.df['cls'] == 'coordinate'].copy()
        
        if len(coords) < 2:
            return regions
        
        # Group by page
        for page in coords['page'].unique():
            page_coords = coords[coords['page'] == page].copy()
            
            # Sort by coordinate value
            if 'coord_value' in page_coords.columns:
                page_coords = page_coords.sort_values('coord_value')
                
                for i in range(len(page_coords) - 1):
                    curr = page_coords.iloc[i]
                    next_coord = page_coords.iloc[i + 1]
                    
                    curr_val = curr.get('coord_value')
                    next_val = next_coord.get('coord_value')
                    
                    if pd.isna(curr_val) or pd.isna(next_val):
                        continue
                    
                    gap = abs(next_val - curr_val)
                    
                    # If gap is large (e.g., 10.5 → 13.8 = 3.3km gap)
                    if gap > 2.0:  # More than 2km gap
                        # Estimate where missing coordinate should be
                        expected_val = (curr_val + next_val) / 2
                        
                        # Estimate position (interpolate between current and next)
                        curr_x = curr.get('xc', 0)
                        curr_y = curr.get('yc', 0)
                        next_x = next_coord.get('xc', 0)
                        next_y = next_coord.get('yc', 0)
                        
                        est_x = (curr_x + next_x) / 2
                        est_y = (curr_y + next_y) / 2
                        
                        # Create region
                        bbox_size = 200  # Search area size
                        
                        regions.append(MissingDetectionRegion(
                            region_type='coordinate_gap',
                            expected_class='coordinate',
                            bbox=(est_x - bbox_size/2, est_y - bbox_size/2, 
                                  est_x + bbox_size/2, est_y + bbox_size/2),
                            center=(est_x, est_y),
                            confidence=min(0.9, gap / 5.0),  # Higher confidence for larger gaps
                            reason=f"Koordinatenlücke: {curr_val:.1f}km → {next_val:.1f}km (Δ{gap:.1f}km). Erwartete Koordinate: ~{expected_val:.1f}km",
                            page=int(page),
                            context={
                                'prev_coord': curr_val,
                                'next_coord': next_val,
                                'gap_km': gap,
                                'expected_value': expected_val
                            }
                        ))
        
        return regions
    
    def _find_orphaned_objects(self, max_distance: float = 600) -> List[MissingDetectionRegion]:
        """
        Find signals/GKS/switches without nearby coordinates.
        Suggests where a coordinate might be missing.
        """
        regions = []
        
        coords = self.df[self.df['cls'] == 'coordinate']
        
        if coords.empty:
            return regions
        
        coord_positions = coords[['xc', 'yc']].values
        
        # Check objects that need coordinates
        need_coords = ['signal', 'gks_gesteuert', 'gks_festkodiert', 'weichen_block']
        
        for cls in need_coords:
            cls_df = self.df[self.df['cls'] == cls]
            
            for _, row in cls_df.iterrows():
                if pd.isna(row.get('xc')) or pd.isna(row.get('yc')):
                    continue
                
                obj_pos = np.array([row['xc'], row['yc']])
                
                # Find nearest coordinate
                distances = np.linalg.norm(coord_positions - obj_pos, axis=1)
                min_dist = distances.min() if len(distances) > 0 else float('inf')
                
                if min_dist > max_distance:
                    # Suggest coordinate location near this object
                    # Typically coordinates are above/below the object
                    search_offset = 150
                    
                    regions.append(MissingDetectionRegion(
                        region_type='orphaned_object',
                        expected_class='coordinate',
                        bbox=(row['xc'] - 100, row['yc'] - search_offset - 50,
                              row['xc'] + 100, row['yc'] + search_offset + 50),
                        center=(row['xc'], row['yc'] - search_offset),
                        confidence=0.7,
                        reason=f"Fehlende Koordinate bei {cls} (nächste Koordinate {min_dist:.0f}px entfernt)",
                        page=int(row['page']),
                        context={
                            'object_class': cls,
                            'object_row_id': int(row['row_id']),
                            'nearest_coord_distance': float(min_dist)
                        }
                    ))
        
        return regions
    
    def _find_pattern_breaks(self) -> List[MissingDetectionRegion]:
        """
        Find breaks in expected patterns.
        E.g., if we have signal-coord-signal-coord-signal-[MISSING]-signal
        """
        regions = []
        
        # Group by page
        for page in self.df['page'].unique():
            page_df = self.df[self.df['page'] == page].copy()
            
            # Sort by vertical position (top to bottom)
            page_df = page_df.sort_values('yc')
            
            # Look for signal/GKS clusters without coordinates
            signals = page_df[page_df['cls'].isin(['signal', 'gks_gesteuert', 'gks_festkodiert'])]
            coords = page_df[page_df['cls'] == 'coordinate']
            
            if len(signals) < 3 or len(coords) < 2:
                continue
            
            # Find vertical gaps in coordinates
            coord_y_positions = sorted(coords['yc'].values)
            
            for i in range(len(coord_y_positions) - 1):
                y1 = coord_y_positions[i]
                y2 = coord_y_positions[i + 1]
                gap = y2 - y1
                
                # If there's a large vertical gap
                if gap > 800:
                    # Check if there are signals in this gap
                    signals_in_gap = signals[(signals['yc'] > y1) & (signals['yc'] < y2)]
                    
                    if len(signals_in_gap) > 0:
                        # There are signals but no coordinate - likely missing
                        mid_y = (y1 + y2) / 2
                        avg_x = signals_in_gap['xc'].mean()
                        
                        regions.append(MissingDetectionRegion(
                            region_type='pattern_break',
                            expected_class='coordinate',
                            bbox=(avg_x - 150, mid_y - 100, avg_x + 150, mid_y + 100),
                            center=(avg_x, mid_y),
                            confidence=0.8,
                            reason=f"Koordinatenlücke: {len(signals_in_gap)} Objekte ohne Koordinate (Lücke: {gap:.0f}px)",
                            page=int(page),
                            context={
                                'objects_in_gap': int(len(signals_in_gap)),
                                'gap_size': float(gap)
                            }
                        ))
        
        return regions