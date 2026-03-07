"""
Component Interfaces - Abstract base classes for modular pipeline components

This module defines the interfaces (abstract base classes) for the main components
of the railway plan extraction pipeline. These interfaces enable:

1. Swappable implementations (e.g., YOLO vs Faster R-CNN)
2. Future extensibility (e.g., LLM-based linking, cloud OCR)
3. Plugin architecture for custom components
4. Dependency injection and testability

Interfaces:
    IDetector: Object detection (YOLO, Faster R-CNN, etc.)
    ILinker: Symbol-coordinate linking (rule-based, ML-based, LLM-based)
    IOCREngine: Text recognition (PaddleOCR, Tesseract, Google Vision)
    IValidator: Result validation (rule-based, LLM-based)
    IStorageBackend: Data persistence (local files, databases, cloud)

Factory:
    ComponentFactory: Creates component instances from configuration
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Tuple, TYPE_CHECKING
from dataclasses import dataclass
import numpy as np
from PIL import Image

if TYPE_CHECKING:
    from core.config_models import LayoutConfig


# ============================================================================
# DETECTOR INTERFACE
# ============================================================================

class IDetector(ABC):
    """
    Abstract interface for object detection components.

    Implementations:
        - YOLODetector: YOLO-based detection (current implementation)
        - FasterRCNNDetector: Faster R-CNN detection (future)
        - TwoStageDetector: Proposal + classification (future)
    """

    @abstractmethod
    def detect(self, image: np.ndarray, config: 'LayoutConfig' = None) -> List[Dict[str, Any]]:
        """
        Detect objects in an image.

        Args:
            image: BGR numpy array
            config: Optional LayoutConfig for detection parameters

        Returns:
            List of detection dicts with keys:
                - name: class name
                - x1, y1, x2, y2: bounding box
                - confidence: detection confidence
                - angle: rotation angle (optional)
        """
        pass

    @abstractmethod
    def get_supported_classes(self) -> List[str]:
        """Return list of classes this detector can identify."""
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """Return detector name for logging/display."""
        pass


class YOLODetector(IDetector):
    """YOLO-based object detection implementation."""

    def __init__(self, model_path: str):
        self.model_path = model_path
        self._model = None
        self._classes = []

    def _load_model(self):
        """Lazy load the YOLO model."""
        if self._model is None:
            from ultralytics import YOLO
            self._model = YOLO(self.model_path)
            if hasattr(self._model, 'names') and self._model.names:
                self._classes = list(self._model.names.values())

    def detect(self, image: np.ndarray, config: 'LayoutConfig' = None) -> List[Dict[str, Any]]:
        """Detect objects using YOLO."""
        self._load_model()
        from core.yolo_detection import run_combined_detection
        return run_combined_detection(self._model, image, config, detect_custom=True)

    def get_supported_classes(self) -> List[str]:
        self._load_model()
        return self._classes

    @property
    def name(self) -> str:
        return "YOLO"


# ============================================================================
# LINKER INTERFACE
# ============================================================================

class ILinker(ABC):
    """
    Abstract interface for symbol-coordinate linking components.

    Implementations:
        - RuleBasedLinker: Spatial rules (current implementation)
        - MLBasedLinker: Machine learning-based linking (future)
        - LLMBasedLinker: LLM-based spatial reasoning (future)
    """

    @abstractmethod
    def link(self, anchor: Dict[str, Any], candidates: List[Dict[str, Any]],
             config: 'LayoutConfig' = None) -> Optional[Dict[str, Any]]:
        """
        Link an anchor symbol to its coordinate.

        Args:
            anchor: Symbol detection dict
            candidates: List of candidate coordinate detections
            config: Optional LayoutConfig for linking parameters

        Returns:
            Best matching coordinate dict, or None if no match
        """
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """Return linker name for logging/display."""
        pass


class RuleBasedLinker(ILinker):
    """Rule-based spatial linking implementation."""

    def link(self, anchor: Dict[str, Any], candidates: List[Dict[str, Any]],
             config: 'LayoutConfig' = None) -> Optional[Dict[str, Any]]:
        """Link using spatial rules."""
        from core.linking import link_anchor_to_coord
        return link_anchor_to_coord(anchor, candidates, config)

    @property
    def name(self) -> str:
        return "RuleBased"


# ============================================================================
# OCR ENGINE INTERFACE
# ============================================================================

class IOCREngine(ABC):
    """
    Abstract interface for OCR (text recognition) components.

    Implementations:
        - PaddleOCREngine: PaddleOCR-based recognition (current)
        - TesseractOCREngine: Tesseract-based recognition
        - EasyOCREngine: EasyOCR-based recognition
        - GoogleVisionOCREngine: Cloud-based Google Vision (future)
    """

    @abstractmethod
    def recognize(self, image: Image.Image, class_name: str = "default") -> Tuple[str, float]:
        """
        Recognize text in an image.

        Args:
            image: PIL Image to process
            class_name: Class name for class-specific processing

        Returns:
            Tuple of (recognized_text, confidence)
        """
        pass

    @abstractmethod
    def recognize_coordinate(self, detection: Dict[str, Any], bgr_image: np.ndarray) -> str:
        """
        Recognize coordinate text from a detection.

        Args:
            detection: Detection dict with bounding box
            bgr_image: Full BGR image

        Returns:
            Recognized coordinate text
        """
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """Return OCR engine name for logging/display."""
        pass


class PaddleOCREngine(IOCREngine):
    """PaddleOCR-based text recognition implementation."""

    def recognize(self, image: Image.Image, class_name: str = "default") -> Tuple[str, float]:
        """Recognize text using PaddleOCR."""
        from core.ocr_engine import paddleocr_recognize
        return paddleocr_recognize(image, class_name)

    def recognize_coordinate(self, detection: Dict[str, Any], bgr_image: np.ndarray) -> str:
        """Recognize coordinate using PaddleOCR."""
        from core.ocr_engine import ocr_coordinate_unified
        return ocr_coordinate_unified(detection, bgr_image, "paddleocr", debug_class="coordinate")

    @property
    def name(self) -> str:
        return "PaddleOCR"


# ============================================================================
# VALIDATOR INTERFACE
# ============================================================================

class IValidator(ABC):
    """
    Abstract interface for result validation components.

    Implementations:
        - RuleBasedValidator: Regex pattern validation (current)
        - LLMValidator: LLM-based semantic validation (future)
    """

    @abstractmethod
    def validate(self, text: str, class_name: str, config: 'LayoutConfig' = None) -> bool:
        """
        Validate recognized text for a given class.

        Args:
            text: Recognized text to validate
            class_name: Class name for class-specific validation
            config: Optional LayoutConfig for validation patterns

        Returns:
            True if valid, False otherwise
        """
        pass

    @abstractmethod
    def get_pattern(self, class_name: str) -> Optional[str]:
        """Get validation pattern for a class."""
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """Return validator name for logging/display."""
        pass


class RuleBasedValidator(IValidator):
    """Regex-based validation implementation."""

    def validate(self, text: str, class_name: str, config: 'LayoutConfig' = None) -> bool:
        """Validate using regex patterns."""
        import re
        pattern = self.get_pattern(class_name, config)
        if pattern is None:
            return True  # No pattern means no validation required
        try:
            return bool(re.match(pattern, text, re.IGNORECASE))
        except Exception:
            return False

    def get_pattern(self, class_name: str, config: 'LayoutConfig' = None) -> Optional[str]:
        """Get pattern from config or use defaults."""
        # Try config patterns first
        if config and config.validation and config.validation.class_id_patterns:
            pattern = config.validation.class_id_patterns.get(class_name)
            if pattern:
                return pattern

        # Fall back to defaults
        default_patterns = {
            "signal": r"^[A-ZÄÖÜ]{1,4}\d{1,4}$",
            "gks_gesteuert": r"^\d{3,4}$",
            "gks_festkodiert": r"^\d{3,4}$",
        }
        return default_patterns.get(class_name)

    @property
    def name(self) -> str:
        return "RuleBased"


# ============================================================================
# STORAGE BACKEND INTERFACE
# ============================================================================

class IStorageBackend(ABC):
    """
    Abstract interface for data persistence components.

    Implementations:
        - LocalFileStorage: CSV/JSON file storage (current)
        - SQLiteStorage: SQLite database storage
        - PostgreSQLStorage: PostgreSQL database storage (future)
        - S3Storage: AWS S3 cloud storage (future)
    """

    @abstractmethod
    def save(self, data: Any, identifier: str) -> bool:
        """
        Save data to storage.

        Args:
            data: Data to save (DataFrame, dict, etc.)
            identifier: Unique identifier for the data

        Returns:
            True if successful, False otherwise
        """
        pass

    @abstractmethod
    def load(self, identifier: str) -> Optional[Any]:
        """
        Load data from storage.

        Args:
            identifier: Unique identifier for the data

        Returns:
            Loaded data, or None if not found
        """
        pass

    @abstractmethod
    def exists(self, identifier: str) -> bool:
        """Check if data exists in storage."""
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """Return storage backend name for logging/display."""
        pass


class LocalFileStorage(IStorageBackend):
    """Local file system storage implementation."""

    def __init__(self, base_path: str = "."):
        self.base_path = base_path

    def save(self, data: Any, identifier: str) -> bool:
        """Save to local file."""
        import os
        import pandas as pd

        filepath = os.path.join(self.base_path, identifier)
        try:
            if isinstance(data, pd.DataFrame):
                data.to_csv(filepath + ".csv", index=False)
            else:
                import json
                with open(filepath + ".json", 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
            return True
        except Exception:
            return False

    def load(self, identifier: str) -> Optional[Any]:
        """Load from local file."""
        import os
        import pandas as pd

        csv_path = os.path.join(self.base_path, identifier + ".csv")
        json_path = os.path.join(self.base_path, identifier + ".json")

        try:
            if os.path.exists(csv_path):
                return pd.read_csv(csv_path)
            elif os.path.exists(json_path):
                import json
                with open(json_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception:
            pass
        return None

    def exists(self, identifier: str) -> bool:
        """Check if file exists."""
        import os
        csv_path = os.path.join(self.base_path, identifier + ".csv")
        json_path = os.path.join(self.base_path, identifier + ".json")
        return os.path.exists(csv_path) or os.path.exists(json_path)

    @property
    def name(self) -> str:
        return "LocalFile"


# ============================================================================
# COMPONENT FACTORY
# ============================================================================

class ComponentFactory:
    """
    Factory for creating pipeline components from configuration.

    Usage:
        factory = ComponentFactory()
        detector = factory.create_detector("yolo", model_path="model.pt")
        linker = factory.create_linker("rule_based")
        ocr = factory.create_ocr_engine("paddleocr")
    """

    _detector_registry: Dict[str, type] = {
        "yolo": YOLODetector,
    }

    _linker_registry: Dict[str, type] = {
        "rule_based": RuleBasedLinker,
    }

    _ocr_registry: Dict[str, type] = {
        "paddleocr": PaddleOCREngine,
    }

    _validator_registry: Dict[str, type] = {
        "rule_based": RuleBasedValidator,
    }

    _storage_registry: Dict[str, type] = {
        "local_file": LocalFileStorage,
    }

    @classmethod
    def register_detector(cls, name: str, detector_class: type):
        """Register a custom detector implementation."""
        cls._detector_registry[name.lower()] = detector_class

    @classmethod
    def register_linker(cls, name: str, linker_class: type):
        """Register a custom linker implementation."""
        cls._linker_registry[name.lower()] = linker_class

    @classmethod
    def register_ocr_engine(cls, name: str, ocr_class: type):
        """Register a custom OCR engine implementation."""
        cls._ocr_registry[name.lower()] = ocr_class

    @classmethod
    def register_validator(cls, name: str, validator_class: type):
        """Register a custom validator implementation."""
        cls._validator_registry[name.lower()] = validator_class

    @classmethod
    def register_storage(cls, name: str, storage_class: type):
        """Register a custom storage backend implementation."""
        cls._storage_registry[name.lower()] = storage_class

    @classmethod
    def create_detector(cls, detector_type: str, **kwargs) -> IDetector:
        """Create a detector instance."""
        detector_class = cls._detector_registry.get(detector_type.lower())
        if detector_class is None:
            raise ValueError(f"Unknown detector type: {detector_type}")
        return detector_class(**kwargs)

    @classmethod
    def create_linker(cls, linker_type: str, **kwargs) -> ILinker:
        """Create a linker instance."""
        linker_class = cls._linker_registry.get(linker_type.lower())
        if linker_class is None:
            raise ValueError(f"Unknown linker type: {linker_type}")
        return linker_class(**kwargs)

    @classmethod
    def create_ocr_engine(cls, ocr_type: str, **kwargs) -> IOCREngine:
        """Create an OCR engine instance."""
        ocr_class = cls._ocr_registry.get(ocr_type.lower())
        if ocr_class is None:
            raise ValueError(f"Unknown OCR engine type: {ocr_type}")
        return ocr_class(**kwargs)

    @classmethod
    def create_validator(cls, validator_type: str, **kwargs) -> IValidator:
        """Create a validator instance."""
        validator_class = cls._validator_registry.get(validator_type.lower())
        if validator_class is None:
            raise ValueError(f"Unknown validator type: {validator_type}")
        return validator_class(**kwargs)

    @classmethod
    def create_storage(cls, storage_type: str, **kwargs) -> IStorageBackend:
        """Create a storage backend instance."""
        storage_class = cls._storage_registry.get(storage_type.lower())
        if storage_class is None:
            raise ValueError(f"Unknown storage type: {storage_type}")
        return storage_class(**kwargs)

    @classmethod
    def create_from_config(cls, config: 'LayoutConfig', model_path: str = None) -> Dict[str, Any]:
        """
        Create all components from a LayoutConfig.

        Args:
            config: LayoutConfig with component selections
            model_path: Path to detector model (if applicable)

        Returns:
            Dict with keys: detector, linker, ocr_engine, validator, storage
        """
        components = {}

        # Create detector
        if model_path and hasattr(config, 'components'):
            detector_type = config.components.detector
            components['detector'] = cls.create_detector(detector_type, model_path=model_path)
        else:
            components['detector'] = None

        # Create linker
        if hasattr(config, 'components'):
            linker_type = config.components.linker
            components['linker'] = cls.create_linker(linker_type)
        else:
            components['linker'] = cls.create_linker("rule_based")

        # Create OCR engine
        if hasattr(config, 'components'):
            ocr_type = config.components.ocr_engine
            components['ocr_engine'] = cls.create_ocr_engine(ocr_type)
        else:
            components['ocr_engine'] = cls.create_ocr_engine("paddleocr")

        # Create validator
        if hasattr(config, 'components'):
            validator_type = config.components.validator
            components['validator'] = cls.create_validator(validator_type)
        else:
            components['validator'] = cls.create_validator("rule_based")

        # Create storage backends
        if hasattr(config, 'components') and config.components.storage:
            components['storage'] = [
                cls.create_storage(st) for st in config.components.storage
            ]
        else:
            components['storage'] = [cls.create_storage("local_file")]

        return components
