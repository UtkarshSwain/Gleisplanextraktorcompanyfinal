"""
Profile management system for loading and validating YAML configuration profiles.

This module provides the ProfileManager class for loading layout-specific
configurations from YAML files into LayoutConfig objects.
"""

import yaml
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
import logging
import os

from core.config_models import (
    LayoutConfig, ClassDefinition, LinkingRule, NameSearchRule,
    DetectionConfig, OCRConfig, SpatialConfig, ValidationConfig,
    ComponentConfig, UIConfig, UIColumnConfig, DEFAULT_UI_CONFIG
)

logger = logging.getLogger(__name__)


class ProfileValidationError(Exception):
    """Raised when profile YAML is invalid"""
    pass


class ProfileManager:
    """
    Manages loading and validation of layout configuration profiles.

    Usage:
        config = ProfileManager.load_profile("profiles/wien_track_plans.yaml")
        # config is now a LayoutConfig object with all parameters
    """

    @staticmethod
    def load_profile(profile_path: str) -> LayoutConfig:
        """
        Load a layout configuration profile from YAML file.

        Args:
            profile_path: Path to YAML profile file

        Returns:
            LayoutConfig object with all parameters loaded

        Raises:
            ProfileValidationError: If YAML is invalid or missing required fields
            FileNotFoundError: If profile file doesn't exist
        """
        path = Path(profile_path)

        if not path.exists():
            raise FileNotFoundError(f"Profile not found: {profile_path}")

        logger.info(f"Loading profile from: {profile_path}")

        with open(path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)

        if not data:
            raise ProfileValidationError(f"Empty profile file: {profile_path}")

        try:
            config = ProfileManager._parse_profile(data)
            config.compile_regex_patterns()

            logger.info(f"Profile loaded: {config.profile_name} v{config.profile_version}")
            logger.info(f"  Classes: {len(config.classes)}")
            logger.info(f"  DPI: {config.detection.dpi}, Tile size: {config.detection.tile_size}")

            return config

        except Exception as e:
            raise ProfileValidationError(f"Failed to parse profile: {e}") from e

    @staticmethod
    def _parse_profile(data: Dict[str, Any]) -> LayoutConfig:
        """Parse YAML data into LayoutConfig object"""

        # Parse metadata
        profile_name = data.get('profile_name', 'default')
        profile_version = data.get('profile_version', '1.0')
        description = data.get('description', '')

        # Parse class definitions
        classes = ProfileManager._parse_classes(data.get('classes', []))

        # Parse component configs
        detection = ProfileManager._parse_detection(data.get('detection', {}))
        ocr = ProfileManager._parse_ocr(data.get('ocr', {}))
        spatial = ProfileManager._parse_spatial(data.get('spatial', {}))
        validation = ProfileManager._parse_validation(data.get('validation', {}))
        components = ProfileManager._parse_components(data.get('components', {}),
                                                       data.get('component_config', {}))

        # Parse UI configuration (modular columns per profile)
        ui = ProfileManager._parse_ui(data.get('ui', {}))

        # Parse optional fields
        model_path = data.get('model_path')
        aliases = data.get('aliases', {})
        class_remap = data.get('class_remap', {})

        # Debug flags
        debug_signals = data.get('debug_signals', False)
        debug_angle_routing = data.get('debug_angle_routing', False)
        debug_ocr = data.get('debug_ocr', False)
        debug_linking = data.get('debug_linking', False)
        debug_track = data.get('debug_track', False)
        debug_custom_symbols = data.get('debug_custom_symbols', False)
        debug_yolo = data.get('debug_yolo', False)
        debug_ui_bbox = data.get('debug_ui_bbox', False)
        debug_comparison = data.get('debug_comparison', False)
        debug_crops = data.get('debug_crops', False)

        # System settings
        poppler_path = data.get('poppler_path')
        zoom_size = data.get('zoom_size', 2048)

        config = LayoutConfig(
            profile_name=profile_name,
            profile_version=profile_version,
            description=description,
            classes=classes,
            aliases=aliases,
            class_remap=class_remap,
            detection=detection,
            ocr=ocr,
            spatial=spatial,
            validation=validation,
            components=components,
            ui=ui,
            model_path=model_path,
            debug_signals=debug_signals,
            debug_angle_routing=debug_angle_routing,
            debug_ocr=debug_ocr,
            debug_linking=debug_linking,
            debug_track=debug_track,
            debug_custom_symbols=debug_custom_symbols,
            debug_yolo=debug_yolo,
            debug_ui_bbox=debug_ui_bbox,
            debug_comparison=debug_comparison,
            debug_crops=debug_crops,
            poppler_path=poppler_path,
            zoom_size=zoom_size
        )

        return config

    @staticmethod
    def _parse_classes(classes_data: list) -> List[ClassDefinition]:
        """Parse class definitions from YAML"""
        classes = []

        for i, cls_data in enumerate(classes_data):
            if isinstance(cls_data, str):
                # Simple string format: just class name
                cls = ClassDefinition(name=cls_data, class_id=i)
            elif isinstance(cls_data, dict):
                # Full format with all parameters
                name = cls_data.get('name')
                if not name:
                    raise ProfileValidationError(f"Class {i} missing 'name' field")

                cls = ClassDefinition(
                    name=name,
                    class_id=cls_data.get('class_id', i),
                    confidence_threshold=cls_data.get('confidence_threshold', 0.5),
                    nms_threshold=cls_data.get('nms_threshold', 0.4),
                    requires_ocr=cls_data.get('requires_ocr', True),
                    requires_coordinate=cls_data.get('requires_coordinate', False),
                    fixed_text=cls_data.get('fixed_text'),
                    numeric_ok=cls_data.get('numeric_ok', False),
                    id_pattern=cls_data.get('id_pattern'),
                    alias=cls_data.get('alias'),
                    linking_rule=ProfileManager._parse_linking_rule(
                        cls_data.get('linking_rule', {})
                    ),
                    name_search_rule=ProfileManager._parse_name_search_rule(
                        cls_data.get('name_search_rule', {})
                    )
                )
            else:
                raise ProfileValidationError(f"Invalid class format at index {i}")

            classes.append(cls)

        return classes

    @staticmethod
    def _parse_linking_rule(rule_data: dict) -> LinkingRule:
        """Parse linking rule from YAML"""
        return LinkingRule(
            mode=rule_data.get('mode', 'below'),
            dx_multiplier=rule_data.get('dx_multiplier', 1.0),
            dy_multiplier=rule_data.get('dy_multiplier', 1.0),
            prefer_horizontal=rule_data.get('prefer_horizontal', False),
            search_left=rule_data.get('search_left', False),
            tilted_ok=rule_data.get('tilted_ok', False),
            block=rule_data.get('block', False),
            fallback_dy_steps=rule_data.get('fallback_dy_steps', [])
        )

    @staticmethod
    def _parse_name_search_rule(rule_data: dict) -> NameSearchRule:
        """Parse name search rule from YAML"""
        return NameSearchRule(
            inside=rule_data.get('inside', False),
            left=rule_data.get('left', False),
            right=rule_data.get('right', False),
            below=rule_data.get('below', False),
            above=rule_data.get('above', False)
        )

    @staticmethod
    def _parse_detection(det_data: dict) -> DetectionConfig:
        """Parse detection config from YAML"""
        return DetectionConfig(
            tile_size=det_data.get('tile_size', 2048),
            overlap_pct=det_data.get('overlap_pct', 40),
            dpi=det_data.get('dpi', 500),
            pred_imgsz=det_data.get('pred_imgsz', 1024),
            tile_halo=det_data.get('tile_halo', 320),
            obb_only=det_data.get('obb_only', True),
            exclude_legend_strip=det_data.get('exclude_legend_strip', True),
            legend_strip_width_percent=det_data.get('legend_strip_width_percent', 12),
            legend_strip_max_pixels=det_data.get('legend_strip_max_pixels', 4200),
            title_block_margin_height=det_data.get('title_block_margin_height', 100),
            title_block_margin_height_default=det_data.get('title_block_margin_height_default', 25),
            title_block_margin_width_default=det_data.get('title_block_margin_width_default', 8),
            # 4-sided cropping
            crop_top=det_data.get('crop_top', 0),
            crop_bottom=det_data.get('crop_bottom', 0),
            crop_left=det_data.get('crop_left', 0),
            crop_right=det_data.get('crop_right', 0),
            use_tta=det_data.get('use_tta', True),
            tta_scales=det_data.get('tta_scales', [1.0]),
            tta_flips=det_data.get('tta_flips', [0, 1]),
            tta_min_votes=det_data.get('tta_min_votes', 1),
            uncertain_thresh_multiplier=det_data.get('uncertain_thresh_multiplier', 0.5),
            min_uncertain_thresh_default=det_data.get('min_uncertain_thresh_default', 0.10),
            min_uncertain_thresh=det_data.get('min_uncertain_thresh', {
                "coordinate": 0.01,
                "isolierstoß": 0.01,
            }),
            # Antwerp-specific detection features
            global_conf_threshold=det_data.get('global_conf_threshold', 0.01),
            use_ink_filter=det_data.get('use_ink_filter', False),
            ink_threshold=det_data.get('ink_threshold', 0.012),
            use_centroid_halo=det_data.get('use_centroid_halo', False),
            halo_ratio=det_data.get('halo_ratio', 0.12),
            halo_conf_boost=det_data.get('halo_conf_boost', 0.50),
            filter_contained_boxes=det_data.get('filter_contained_boxes', False),
            contained_box_threshold=det_data.get('contained_box_threshold', 0.80),
            prefer_larger_nms=det_data.get('prefer_larger_nms', False),
            # Batch inference parameters
            batch_size=det_data.get('batch_size', 1),
            yolo_workers=det_data.get('yolo_workers', 0),
            # Polygon handling (Antwerp fix)
            use_native_obb_polygons=det_data.get('use_native_obb_polygons', False),
            # Halo expansion (default True = current behavior for Wien)
            use_halo_expansion=det_data.get('use_halo_expansion', True),
        )

    @staticmethod
    def _parse_ocr(ocr_data: dict) -> OCRConfig:
        """Parse OCR config from YAML"""
        return OCRConfig(
            engine=ocr_data.get('engine', 'paddleocr'),
            max_workers=ocr_data.get('max_workers', 8),
            tesseract_path=ocr_data.get('tesseract_path'),
            sig_one_window=ocr_data.get('sig_one_window', True),
            sig_pad=ocr_data.get('sig_pad', 14),
            sig_expand_x=ocr_data.get('sig_expand_x', 0.18),
            sig_expand_y=ocr_data.get('sig_expand_y', 0.22),
            sig_use_tighten=ocr_data.get('sig_use_tighten', False),
            sig_score_min=ocr_data.get('sig_score_min', 1.3),
            sig_line_thick=ocr_data.get('sig_line_thick', 5),
            signal_text_height_hint=ocr_data.get('signal_text_height_hint'),
            left_bias_expansion_classes=set(ocr_data.get('left_bias_expansion_classes', ['signal'])),
            left_bias_ratio_h=ocr_data.get('left_bias_ratio_h', 0.8),
            angle_tol=ocr_data.get('angle_tol', 12.0),
            denoise_strength=ocr_data.get('denoise_strength', 4),
            sharpen_amount=ocr_data.get('sharpen_amount', 1.3),
            use_preprocessing=ocr_data.get('use_preprocessing', True),
            use_adaptive_threshold=ocr_data.get('use_adaptive_threshold', True),
            use_morph_operations=ocr_data.get('use_morph_operations', True),
            use_simple_ocr=ocr_data.get('use_simple_ocr', False),
            simple_ocr_padding=ocr_data.get('simple_ocr_padding', {
                "coordinate": 3,
                "text_id": 4,
                "default": 4
            }),
            confidence_thresholds=ocr_data.get('confidence_thresholds', {
                "signal": 0.50,
                "gks_gesteuert": 0.40,
                "gks_festkodiert": 0.40,
                "coordinate": 0.65,
                "default": 0.45
            }),
            cardinal_detection_padding=ocr_data.get('cardinal_detection_padding', {}),
            cardinal_expansion_factor=ProfileManager._parse_tuple_dict(
                ocr_data.get('cardinal_expansion_factor', {})
            ),
            angular_detection_padding=ocr_data.get('angular_detection_padding', {}),
            angular_expansion_factor=ProfileManager._parse_tuple_dict(
                ocr_data.get('angular_expansion_factor', {})
            )
        )

    @staticmethod
    def _parse_spatial(spatial_data: dict) -> SpatialConfig:
        """Parse spatial config from YAML"""
        return SpatialConfig(
            enable_track_detection=spatial_data.get('enable_track_detection', True),
            signal_dy_multiplier=spatial_data.get('signal_dy_multiplier', 2.2),
            signal_dx_multiplier=spatial_data.get('signal_dx_multiplier', 2.4),
            default_dy_multiplier=spatial_data.get('default_dy_multiplier', 1.6),
            default_dx_multiplier=spatial_data.get('default_dx_multiplier', 1.0),
            signal_extended_dx_ratio=spatial_data.get('signal_extended_dx_ratio', 5.0),
            text_id_search_steps=spatial_data.get('text_id_search_steps', [1.0, 1.5, 2.0, 2.5, 3.0, 3.5]),
            inside_padding_ratio=spatial_data.get('inside_padding_ratio', 0.10),
            right_window_width_ratio=spatial_data.get('right_window_width_ratio', 2.5),
            right_window_height_ratio=spatial_data.get('right_window_height_ratio', 0.6),
            left_window_width_ratio=spatial_data.get('left_window_width_ratio', 4.0),
            left_window_height_ratio=spatial_data.get('left_window_height_ratio', 0.6),
            sverbinder_window_width_ratio=spatial_data.get('sverbinder_window_width_ratio', 0.9),
            sverbinder_window_height_ratio=spatial_data.get('sverbinder_window_height_ratio', 0.3),
            dy_max_base_multiplier=spatial_data.get('dy_max_base_multiplier', 1.6),
            dx_base_multiplier=spatial_data.get('dx_base_multiplier', 0.6),
            dx_tight_multiplier=spatial_data.get('dx_tight_multiplier', 0.45),
            dx_minimum_threshold=spatial_data.get('dx_minimum_threshold', 30),
            left_search_bonus=spatial_data.get('left_search_bonus', 1.3),
            haltetafel_gks_max_distance=spatial_data.get('haltetafel_gks_max_distance', 250),
            haltetafel_gks_dy_tolerance=spatial_data.get('haltetafel_gks_dy_tolerance', 100),
            haltetafel_gks_dx_tolerance=spatial_data.get('haltetafel_gks_dx_tolerance', 300),
            signal_gks_max_distance=spatial_data.get('signal_gks_max_distance', 250),
            signal_gks_dy_min=spatial_data.get('signal_gks_dy_min', 30),
            signal_gks_dy_max=spatial_data.get('signal_gks_dy_max', 200),
            signal_gks_dx_tolerance_left=spatial_data.get('signal_gks_dx_tolerance_left', 120),
            signal_gks_dx_tolerance_right=spatial_data.get('signal_gks_dx_tolerance_right', 120),
            signal_gks_angle_tolerance=spatial_data.get('signal_gks_angle_tolerance', 20.0),
            signal_gks_relaxed_dx_tolerance=spatial_data.get('signal_gks_relaxed_dx_tolerance', 200),
            signal_gks_relaxed_dy_max=spatial_data.get('signal_gks_relaxed_dy_max', 600),
            signal_gks_relaxed_angle_tolerance=spatial_data.get('signal_gks_relaxed_angle_tolerance', 25.0),
            signal_gks_nearest_max_distance=spatial_data.get('signal_gks_nearest_max_distance', 800),
            signal_gks_nearest_angle_tolerance=spatial_data.get('signal_gks_nearest_angle_tolerance', 30.0),
            track_perpendicular_max_distance=spatial_data.get('track_perpendicular_max_distance', 1500),
            track_window_size=spatial_data.get('track_window_size', 25),
            track_search_radius=spatial_data.get('track_search_radius', 500),
            track_sample_distance=spatial_data.get('track_sample_distance', 200),
            haltepunkt_cluster_max_distance=spatial_data.get('haltepunkt_cluster_max_distance', 250),
            haltepunkt_signal_dy_min=spatial_data.get('haltepunkt_signal_dy_min', 30),
            haltepunkt_signal_dy_max=spatial_data.get('haltepunkt_signal_dy_max', 200),
            haltepunkt_coord_dy_min=spatial_data.get('haltepunkt_coord_dy_min', 20),
            haltepunkt_coord_dy_max=spatial_data.get('haltepunkt_coord_dy_max', 150),
            haltepunkt_dx_tolerance=spatial_data.get('haltepunkt_dx_tolerance', 100),
            haltepunkt_angle_tolerance=spatial_data.get('haltepunkt_angle_tolerance', 20.0),
            isolierstoss_fallback_radius=spatial_data.get('isolierstoss_fallback_radius', 300),
            adaptive_search_dx_multiplier=spatial_data.get('adaptive_search_dx_multiplier', 3.0),
            adaptive_search_dx_minimum=spatial_data.get('adaptive_search_dx_minimum', 150),
            adaptive_search_dy_multiplier=spatial_data.get('adaptive_search_dy_multiplier', 3.0),
            adaptive_search_dy_minimum=spatial_data.get('adaptive_search_dy_minimum', 80),
            spatial_threshold_single_section=spatial_data.get('spatial_threshold_single_section', 1000),
            spatial_threshold_gap_multiplier=spatial_data.get('spatial_threshold_gap_multiplier', 3.0),
            spatial_threshold_section_gap_min=spatial_data.get('spatial_threshold_section_gap_min', 1000),
            spatial_threshold_section_gap_max=spatial_data.get('spatial_threshold_section_gap_max', 2500),
            # Coordinate linking settings (Antwerp)
            coord_search_steps=spatial_data.get('coord_search_steps', [1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0, 5.5, 6.0, 6.5, 7.0]),
            coord_dx_steps=spatial_data.get('coord_dx_steps', [5, 10, 15, 20, 25, 30]),
            coord_dy_min=spatial_data.get('coord_dy_min', 30),
            coord_dy_base=spatial_data.get('coord_dy_base', 300),
            coord_phase1_classes=spatial_data.get('coord_phase1_classes', ["s_bond", "short_bond", "terminal_bond", "insulation_joint", "spie_loop"]),
            signal_coord_dx_steps=spatial_data.get('signal_coord_dx_steps', [50, 100, 150, 200, 250]),
            coupling_coil_dx_steps=spatial_data.get('coupling_coil_dx_steps', [5, 10, 15, 20, 25, 30, 40, 50, 60, 70]),
            coupling_coil_dy_steps=spatial_data.get('coupling_coil_dy_steps', [1.0, 1.5, 2.0]),
            # Antwerp-specific: Durchrutschweg calculation parameters
            durchrutschweg_bond_classes=spatial_data.get('durchrutschweg_bond_classes', ["s_bond", "short_bond", "insulation_joint"]),
            durchrutschweg_y_tolerance=spatial_data.get('durchrutschweg_y_tolerance', 30),
            durchrutschweg_first_bond_dy_max=spatial_data.get('durchrutschweg_first_bond_dy_max', 300),
            durchrutschweg_first_bond_dx_max=spatial_data.get('durchrutschweg_first_bond_dx_max', 150)
        )

    @staticmethod
    def _parse_validation(val_data: dict) -> ValidationConfig:
        """Parse validation config from YAML"""
        return ValidationConfig(
            coordinate_pattern=val_data.get('coordinate_pattern',
                r'^\s*([+-]?\d{1,3}[,\.]\d{3,4})\s*(?:(?:GI|Gl)\.?\s*([A-Za-z0-9./-]{1,6}))?\s*$'),
            class_id_patterns=val_data.get('class_id_patterns', {
                "signal": r"^[A-ZÄÖÜ]{1,4}\d{1,4}$",
                "gks_gesteuert": r"^\d{3,4}$",
                "gks_festkodiert": r"^\d{3,4}$",
            }),
            numeric_ok_classes=val_data.get('numeric_ok_classes', [
                "gks_gesteuert", "gks_festkodiert", "weichen_block", "prellbock"
            ]),
            decimal_separator_input=val_data.get('decimal_separator_input', ','),
            decimal_separator_output=val_data.get('decimal_separator_output', '.')
        )

    @staticmethod
    def _parse_components(comp_data: dict, comp_config: dict) -> ComponentConfig:
        """Parse component selection from YAML"""
        storage = comp_data.get('storage', ['local_file'])
        if isinstance(storage, str):
            storage = [storage]

        return ComponentConfig(
            detector=comp_data.get('detector', 'yolo'),
            linker=comp_data.get('linker', 'rule_based'),
            ocr_engine=comp_data.get('ocr_engine', 'paddleocr'),
            validator=comp_data.get('validator', 'rule_based'),
            storage=storage,
            detector_args=comp_config.get('detector_args', {}),
            linker_args=comp_config.get('linker_args', {}),
            ocr_engine_args=comp_config.get('ocr_engine_args', {}),
            validator_args=comp_config.get('validator_args', {}),
            storage_args=comp_config.get('storage_args', {})
        )

    @staticmethod
    def _parse_tuple_dict(data: dict) -> Dict[str, Tuple[float, float]]:
        """Convert dict of lists to dict of tuples (for expansion factors)"""
        result = {}
        for k, v in data.items():
            if isinstance(v, list) and len(v) == 2:
                result[k] = (float(v[0]), float(v[1]))
            elif isinstance(v, tuple):
                result[k] = v
            else:
                result[k] = (1.0, 1.0)  # Default
        return result

    @staticmethod
    def _parse_ui(ui_data: dict) -> UIConfig:
        """Parse UI configuration from YAML (modular columns per profile)"""
        if not ui_data or 'table_columns' not in ui_data:
            # Return default UI config if no UI section defined
            return DEFAULT_UI_CONFIG

        columns = []
        for col_data in ui_data.get('table_columns', []):
            if isinstance(col_data, dict):
                col = UIColumnConfig(
                    name=col_data.get('name', ''),
                    field=col_data.get('field', ''),
                    editor_type=col_data.get('editor_type', 'text'),
                    combo_values=col_data.get('combo_values', []),
                    spin_min=col_data.get('spin_min', 1),
                    spin_max=col_data.get('spin_max', 9999),
                    show_for_classes=col_data.get('show_for_classes', [])
                )
                columns.append(col)

        if not columns:
            return DEFAULT_UI_CONFIG

        return UIConfig(table_columns=columns)

    @staticmethod
    def list_available_profiles(profiles_dir: str = None) -> List[str]:
        """
        List all available profile YAML files.

        Args:
            profiles_dir: Directory containing profile files

        Returns:
            List of profile file paths
        """
        if profiles_dir is None:
            from paths import get_profiles_dir
            profiles_path = get_profiles_dir()
        else:
            profiles_path = Path(profiles_dir)
        if not profiles_path.exists():
            return []

        profiles = []
        for yaml_file in profiles_path.glob("*.yaml"):
            profiles.append(str(yaml_file))
        for yml_file in profiles_path.glob("*.yml"):
            profiles.append(str(yml_file))

        return sorted(profiles)


# Convenience function for loading profiles
def load_profile(profile_path: str) -> LayoutConfig:
    """Load a profile - convenience wrapper"""
    return ProfileManager.load_profile(profile_path)
