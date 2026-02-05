# validation_config.py
"""
Shared Validation Configuration
Single source of truth for all validation thresholds and class requirements.

Used by:
- Erkennungsqualität (quality_inspector.py)
- Datenvalidierung (ultimate_validator.py)
- Counter Bar risk calculation (workspace_widget.py)
"""

from typing import Dict, List, Tuple

# =============================================================================
# CLASS REQUIREMENTS
# =============================================================================

# Classes that MUST have a linked coordinate
# (comprehensive list from Datenvalidierung)
CLASSES_REQUIRING_COORDINATES: List[str] = [
    'signal',
    'gks_gesteuert',
    'gks_festkodiert',
    'isolierstoß',
    'prellblock',
    'haltepunkt',
    'sverbinder',
    'gm_block',
    'haltetafel',
    'weichenende',
    'weichengruppeende',
]

# Classes that MUST have text/label (anchor_text)
CLASSES_REQUIRING_TEXT: List[str] = [
    'signal',
    'gks_gesteuert',
    'gks_festkodiert',
]

# Classes excluded from validation entirely
CLASSES_EXCLUDED: List[str] = [
    'coordinate',      # Standalone coordinates are not validated
    'weichen_block',   # Excluded per user request
]

# =============================================================================
# CONFIDENCE THRESHOLDS
# =============================================================================

# Per-class minimum confidence thresholds for "good" detection
# Below this = flagged for review
CONFIDENCE_THRESHOLDS: Dict[str, float] = {
    "signal": 0.80,
    "gm_block": 0.80,
    "gks_festkodiert": 0.70,
    "gks_gesteuert": 0.70,
    "weichen_block": 0.90,
    "isolierstoß": 0.70,
    "haltepunkt": 0.80,
    "sverbinder": 0.80,
    "coordinate": 0.65,
    "weichenende": 0.80,
    "prellblock": 0.80,
    "haltetafel": 0.70,
    "weichengruppeende": 0.80,
}

# Default threshold for unknown classes
DEFAULT_CONFIDENCE_THRESHOLD: float = 0.60

# =============================================================================
# RISK SCORE CALCULATION
# =============================================================================

# Weight factors for risk score calculation
# Total should add up to ~1.0 for maximum risk
RISK_WEIGHTS: Dict[str, float] = {
    'low_confidence': 0.40,       # Confidence below threshold
    'missing_coordinate': 0.30,   # Missing required coordinate
    'haltepunkt_signal_mismatch': 0.25,  # Haltepunkt references unknown signal
    'invalid_coordinate': 0.20,   # Coordinate doesn't start with digit/-
    'gks_letters': 0.15,          # GKS contains letters (should be numbers)
    'missing_text': 0.15,         # Missing required text/label
    'duplicate_nearby': 0.15,     # Possible duplicate detection
    'size_anomaly': 0.10,         # Unusually small/large
    'formatting_error': 0.05,     # Multiple spaces, etc.
}

# Risk level thresholds
# These determine the traffic light colors
RISK_THRESHOLDS: Dict[str, float] = {
    'high': 0.20,    # > 20% = Red / "Sofort prüfen"
    'medium': 0.10,  # 10-20% = Yellow / "Bald prüfen"
    # < 10% = Green / "Gut erkannt"
}

# =============================================================================
# VALIDATION LABELS (German)
# =============================================================================

RISK_LABELS: Dict[str, str] = {
    'high_risk': 'Sofort prüfen',
    'medium_risk': 'Bald prüfen',
    'low_risk': 'Gut erkannt',
}

# Risk factor descriptions (for UI display)
RISK_FACTOR_LABELS: Dict[str, str] = {
    'low_confidence': 'Unsichere Texterkennung',
    'missing_coordinate': 'Koordinate fehlt',
    'haltepunkt_signal_mismatch': 'Haltepunkt: Signal nicht gefunden',
    'invalid_coordinate': 'Ungültige Koordinate',
    'gks_letters': 'GKS enthält Buchstaben',
    'missing_text': 'Bezeichnung fehlt',
    'duplicate_nearby': 'Evtl. doppelt erkannt',
    'size_anomaly': 'Auffällige Größe',
    'formatting_error': 'Formatierungsfehler',
}

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_confidence_threshold(cls_name: str) -> float:
    """Get confidence threshold for a class (with fallback to default)."""
    return CONFIDENCE_THRESHOLDS.get(cls_name, DEFAULT_CONFIDENCE_THRESHOLD)


def needs_coordinate(cls_name: str) -> bool:
    """Check if a class requires a linked coordinate."""
    return cls_name in CLASSES_REQUIRING_COORDINATES


def needs_text(cls_name: str) -> bool:
    """Check if a class requires text/label."""
    return cls_name in CLASSES_REQUIRING_TEXT


def is_excluded(cls_name: str) -> bool:
    """Check if a class should be excluded from validation."""
    return cls_name in CLASSES_EXCLUDED


def get_risk_level(risk_score: float) -> str:
    """
    Determine risk level from score.

    Returns: 'high_risk', 'medium_risk', or 'low_risk'
    """
    if risk_score > RISK_THRESHOLDS['high']:
        return 'high_risk'
    elif risk_score >= RISK_THRESHOLDS['medium']:
        return 'medium_risk'
    else:
        return 'low_risk'


def get_risk_label(risk_level: str) -> str:
    """Get German label for risk level."""
    return RISK_LABELS.get(risk_level, 'Unbekannt')


def calculate_risk_score(
    confidence: float,
    cls_name: str,
    has_coordinate: bool,
    coordinate_text: str,
    anchor_text: str,
    is_custom_symbol: bool = False,
    custom_config: dict = None,
) -> Tuple[float, List[str]]:
    """
    Calculate risk score using shared configuration.

    Args:
        confidence: Detection confidence (0-1)
        cls_name: Class name
        has_coordinate: Whether coordinate is linked
        coordinate_text: The coordinate text value
        anchor_text: The anchor/label text
        is_custom_symbol: Whether this is a template-matched symbol
        custom_config: Configuration for custom symbols (has_text, links_to_coordinate)

    Returns:
        Tuple of (risk_score, list_of_risk_factors)
    """
    import pandas as pd

    risk = 0.0
    factors = []

    # Determine requirements based on symbol type
    if is_custom_symbol and custom_config:
        requires_coord = custom_config.get('links_to_coordinate', False)
        requires_text = custom_config.get('has_text', False)
    else:
        requires_coord = needs_coordinate(cls_name)
        requires_text = needs_text(cls_name)

    # Factor 1: Confidence Risk
    threshold = get_confidence_threshold(cls_name)
    if pd.notna(confidence):
        if confidence < threshold:
            conf_risk = (1.0 - confidence) * RISK_WEIGHTS['low_confidence']
            risk += conf_risk
            factors.append(RISK_FACTOR_LABELS['low_confidence'])

    # Factor 2: Missing Coordinate
    if requires_coord:
        coord_str = str(coordinate_text).strip() if pd.notna(coordinate_text) else ''
        if not coord_str:
            risk += RISK_WEIGHTS['missing_coordinate']
            factors.append(RISK_FACTOR_LABELS['missing_coordinate'])
        else:
            # Factor 2b: Invalid Coordinate (doesn't start with digit or minus)
            if coord_str and not (coord_str[0].isdigit() or coord_str[0] == '-'):
                risk += RISK_WEIGHTS['invalid_coordinate']
                factors.append(RISK_FACTOR_LABELS['invalid_coordinate'])

    # Factor 3: Missing Text
    if requires_text:
        text_str = str(anchor_text).strip() if pd.notna(anchor_text) else ''
        if not text_str:
            risk += RISK_WEIGHTS['missing_text']
            factors.append(RISK_FACTOR_LABELS['missing_text'])

    # Factor 4: GKS with Letters
    if cls_name in ['gks_gesteuert', 'gks_festkodiert']:
        gks_text = str(anchor_text).strip() if pd.notna(anchor_text) else ''
        if gks_text:
            cleaned = gks_text.replace(' ', '').replace('-', '')
            if cleaned and not cleaned.isdigit():
                risk += RISK_WEIGHTS['gks_letters']
                factors.append(RISK_FACTOR_LABELS['gks_letters'])

    # Factor 5: Formatting Errors (multiple spaces)
    coord_str = str(coordinate_text) if pd.notna(coordinate_text) else ''
    anchor_str = str(anchor_text) if pd.notna(anchor_text) else ''
    if '  ' in coord_str or '  ' in anchor_str:
        risk += RISK_WEIGHTS['formatting_error']
        factors.append(RISK_FACTOR_LABELS['formatting_error'])

    return (min(risk, 1.0), factors)
