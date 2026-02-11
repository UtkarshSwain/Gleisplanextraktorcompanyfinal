# MODULARITY REFACTORING - QUICK START GUIDE

## 📚 DOCUMENTS YOU HAVE

You now have 3 comprehensive documents:

1. **MODULARITY_EXPLAINED.md** - Conceptual guide (read this first to understand WHY)
2. **MODULARITY_IMPLEMENTATION_GUIDE.md** - Technical guide (complete implementation instructions)
3. **MODULARITY_QUICKSTART.md** (this file) - Quick start checklist

---

## ⏱️ TIME REQUIRED

- **Option 2 (Recommended):** 10-14 hours
- **Timeline:** Can be done in 1-2 focused days

---

## ✅ IMPLEMENTATION CHECKLIST

### **PREPARATION (30 minutes)**

- [ ] Read MODULARITY_EXPLAINED.md (understand the concepts)
- [ ] Review current codebase structure
- [ ] Create git branch: `git checkout -b feature/modular-architecture`
- [ ] Commit current state: `git commit -am "Checkpoint before modularity refactoring"`

---

### **PHASE 1: Configuration Architecture (3-4 hours)**

**Files to CREATE:**

- [ ] `core/config_models.py` - LayoutConfig dataclass
  - Define all configuration structures
  - 13 ClassDefinition objects
  - DetectionConfig, OCRConfig, SpatialConfig, ValidationConfig
  - LayoutConfig with helper methods

- [ ] `core/profile_manager.py` - Profile loader/validator
  - ProfileManager class
  - YAML parsing functions
  - Validation and error handling
  - load_profile() function

- [ ] `profiles/db_track_plans.yaml` - Complete standard profile
  - All 13 classes with parameters
  - Detection config (tile_size, dpi, etc.)
  - OCR config (all parameters)
  - Spatial config (all multipliers)
  - Validation patterns

- [ ] `profiles/db_track_plans_strict.yaml` - High precision variant
  - Copy from standard, increase thresholds by +0.10
  - Tighter spatial constraints

- [ ] `profiles/db_track_plans_relaxed.yaml` - High recall variant
  - Copy from standard, decrease thresholds by -0.10
  - Wider spatial search windows

**Test Phase 1:**
```bash
python -c "from core.profile_manager import ProfileManager; config = ProfileManager.load_profile('profiles/db_track_plans.yaml'); print(f'✅ Loaded: {config.profile_name}')"
```

---

### **PHASE 2: Refactor Core Functions (4-5 hours)**

**Files to MODIFY:**

- [ ] `core/yolo_detection.py`
  - Remove: `from config import ...`
  - Add `config: LayoutConfig` parameter to:
    - `run_yolo_on_page(model, page_bgr, config)`
    - `run_combined_detection(model, page_bgr, config, detect_custom)`
    - `tile_image(bgr, config)`
  - Replace all global accesses with `config.xxx`

- [ ] `core/linking.py`
  - Remove: `from config import LINK_RULES, COORD_RE, ...`
  - Add `config: LayoutConfig` parameter to:
    - `name_windows_for(anchor, img_shape, mode, config)`
    - `link_anchor_to_coord(anchor, coords, config, learned_patterns)`
    - `detect_fahrtrichtung(signal_det, gks_dets, config, ...)`
    - `detect_haltepunkt_signal_group(..., config)`
    - `link_haltetafel_to_gks(..., config)`
    - `link_isolierstoss_fallback(..., config)`
    - `parse_coord(text, config)`
    - `merge_duplicate_signals(..., config, ...)`
  - Replace hardcoded values (2.2, 1.6, 250, etc.) with `config.spatial.xxx`

- [ ] `core/ocr_engine.py`
  - Remove: `from config import CARDINAL_PARAMS, SIG_PAD, ...`
  - Add `config: LayoutConfig` parameter to:
    - `ocr_anchor_name(anchor, bgr_color, engine, config)`
    - `ocr_coordinate_unified(det, bgr, engine, config)`
    - `ocr_best_angle(det, bgr, engine, config)`
  - Replace all config globals with `config.ocr.xxx` and `config.validation.xxx`

- [ ] `core/image_processing.py`
  - Minor changes (if uses ZOOM_SIZE)
  - Add config parameter where needed

**Test Phase 2:**
```bash
python -c "from core.yolo_detection import tile_image; from core.profile_manager import ProfileManager; config = ProfileManager.load_profile('profiles/db_track_plans.yaml'); print('✅ Functions accept config')"
```

---

### **PHASE 3: Update PipelineWorker (2-3 hours)**

**Files to MODIFY:**

- [ ] `core/pipelineworker.py`
  - Remove: `from config import POPPLER_PATH, CLASS_THRESH, CLASSES, ...`
  - Add: `from core.config_models import LayoutConfig`
  - Add: `from core.profile_manager import ProfileManager`
  - Modify `__init__`:
    - Add parameter: `layout_config: LayoutConfig`
    - Store as: `self.config = layout_config`
  - Pass `self.config` to ALL function calls:
    - `run_combined_detection(..., self.config, ...)`
    - `ocr_anchor_name(..., self.config)`
    - `link_anchor_to_coord(..., self.config, ...)`
    - All other refactored functions

- [ ] `ui/setup_window.py` OR `ui/workspace_widget.py`
  - Add profile selection UI (combo box or file picker)
  - Load profile before creating worker:
    ```python
    config = ProfileManager.load_profile(profile_path)
    worker = PipelineWorker(pdf_path, model_path, ocr_engine, config)
    ```

**Test Phase 3:**
- [ ] Run full pipeline with standard profile
- [ ] Verify no errors
- [ ] Check results match original implementation

---

### **PHASE 4: Testing & Validation (2-3 hours)**

**Files to CREATE:**

- [ ] `test_modular_pipeline.py` - Test suite
  - Test profile loading
  - Test config parameter access
  - Test pipeline initialization
  - Regression testing

**Run tests:**
```bash
# Test profile loading
python test_modular_pipeline.py

# Test full pipeline (provide PDF and model)
python test_modular_pipeline.py path/to/test.pdf path/to/model.pt
```

**Validation:**
- [ ] All 3 profiles load without errors
- [ ] Pipeline runs end-to-end
- [ ] Results identical to original implementation
- [ ] Different profiles produce different results (as expected)

---

### **PHASE 5: Component Interfaces (OPTIONAL - 2-3 hours)**

**File to CREATE:**

- [ ] `core/interfaces.py` - Component interfaces
  - IDetector interface + YOLODetector implementation
  - ILinker interface + RuleBasedLinker implementation
  - IOCREngine interface + PaddleOCREngine implementation
  - IValidator interface + RuleBasedValidator implementation
  - IStorageBackend interface + LocalFileStorage implementation
  - ComponentFactory for easy instantiation

**Note:** This is the ".5" in Option 2.5 - adds full extensibility for LLMs, neural networks, storage backends.

---

## 🚀 STARTING THE IMPLEMENTATION

### **Method 1: Using Claude Code (Recommended)**

1. Open a new Claude Code chat
2. Paste this prompt:

```
I need to refactor my railway plan extraction pipeline to modular architecture.

Please read and follow this implementation guide:
/home/user/Gleisplanextraktorv3/MODULARITY_IMPLEMENTATION_GUIDE.md

Implement Option 2 (Proper Modular Architecture).
Start with Phase 1: Configuration Architecture.

Create the following files first:
1. core/config_models.py
2. core/profile_manager.py
3. profiles/db_track_plans.yaml

After creating these, I'll review and you can continue with Phase 2.
```

3. Claude Code will read the guide and start implementing
4. Review each phase before proceeding to next

---

### **Method 2: Manual Implementation**

1. Open MODULARITY_IMPLEMENTATION_GUIDE.md
2. Follow Phase 1 instructions
3. Copy code from guide into files
4. Test after each phase
5. Proceed to next phase

---

## 📊 EXPECTED OUTCOMES

### **After Phase 1-3 (Core Modularity):**
- ✅ No more global config dependencies
- ✅ Configuration loaded from YAML files
- ✅ Can process documents with different profiles
- ✅ Pipeline accepts injected config

### **After Phase 4 (Testing):**
- ✅ Regression tests pass
- ✅ 3 profile variants work correctly
- ✅ Results verified against original

### **After Phase 5 (Interfaces - Optional):**
- ✅ Can swap detection models
- ✅ Can integrate LLMs for validation
- ✅ Can plug in different storage backends
- ✅ Fully extensible architecture

---

## 🎯 THESIS BENEFITS

Once modular refactoring is complete, you can write in your thesis:

### **Architecture Chapter:**
"The system employs a modular, profile-based architecture enabling:
- Runtime configuration via YAML profiles
- Component-based design with well-defined interfaces
- Dependency injection for testability and flexibility
- Support for multiple layout types without code modification"

### **Implementation Chapter:**
"To demonstrate configurability, three profile variants were created:
1. Standard (balanced precision/recall)
2. Strict (high precision, lower recall)
3. Relaxed (high recall, lower precision)

Testing on identical documents with different profiles showed measurable differences in detection counts and accuracy metrics."

### **Future Work:**
"The modular architecture enables several extensions:
- LLM-based spatial reasoning via ILinker interface
- Multi-model ensemble detection via IDetector interface
- Cloud storage backends via IStorageBackend interface
- Active learning through confidence-based profile refinement"

---

## 🔧 TROUBLESHOOTING

### **Error: "NameError: name 'TILE_SIZE' is not defined"**
- **Fix:** You forgot to replace a global import with config parameter
- **Where:** Search for `TILE_SIZE` in the file, replace with `config.detection.tile_size`

### **Error: "TypeError: missing required positional argument: 'config'"**
- **Fix:** You called a refactored function without passing config
- **Where:** Add `config` or `self.config` to the function call

### **Error: "ProfileValidationError: Missing required field"**
- **Fix:** YAML profile is incomplete
- **Where:** Compare with db_track_plans.yaml template, add missing fields

### **Error: Results don't match original**
- **Fix:** Config values don't match original hardcoded values
- **Where:** Check YAML values exactly match values from config.py

---

## 📝 GIT WORKFLOW

```bash
# Start
git checkout -b feature/modular-architecture
git commit -am "Checkpoint before modularity"

# After Phase 1
git add core/config_models.py core/profile_manager.py profiles/
git commit -m "Phase 1: Add configuration architecture"

# After Phase 2
git add core/yolo_detection.py core/linking.py core/ocr_engine.py
git commit -m "Phase 2: Refactor core functions to use config"

# After Phase 3
git add core/pipelineworker.py ui/
git commit -m "Phase 3: Update PipelineWorker with dependency injection"

# After Phase 4
git add test_modular_pipeline.py
git commit -m "Phase 4: Add test suite and validation"

# Optional Phase 5
git add core/interfaces.py
git commit -m "Phase 5: Add component interfaces for full extensibility"

# Merge to main branch when done
git checkout test/templatematching
git merge feature/modular-architecture
```

---

## 📚 ADDITIONAL RESOURCES

### **Documents to Read:**
1. **MODULARITY_EXPLAINED.md** - Read first for concepts
2. **MODULARITY_IMPLEMENTATION_GUIDE.md** - Reference during implementation
3. **MODULARITY_QUICKSTART.md** (this file) - Quick checklist

### **Code Files Created:**
- `core/config_models.py` - Configuration dataclasses
- `core/profile_manager.py` - YAML loader
- `core/interfaces.py` - Component interfaces (optional)
- `profiles/*.yaml` - Configuration profiles
- `test_modular_pipeline.py` - Test suite

### **Code Files Modified:**
- `core/yolo_detection.py` - Uses config, not globals
- `core/linking.py` - Uses config, not globals
- `core/ocr_engine.py` - Uses config, not globals
- `core/pipelineworker.py` - Accepts injected config
- `ui/setup_window.py` or `ui/workspace_widget.py` - Loads profiles

---

## ✅ DEFINITION OF DONE

You're finished when:

1. ✅ All core functions accept `config` parameter
2. ✅ No `from config import ...` in core/ files
3. ✅ ProfileManager loads all 3 YAML profiles successfully
4. ✅ PipelineWorker runs end-to-end with injected config
5. ✅ Regression tests pass (results match original)
6. ✅ Different profiles produce measurably different results
7. ✅ No errors/warnings when running test suite
8. ✅ Code committed to git with clear commit messages

---

## 🎓 THESIS TIMELINE

**Remaining 4 weeks breakdown:**

- **Week 1:** Modularity implementation (this work)
  - Days 1-2: Phase 1 (Config architecture)
  - Days 3-4: Phase 2 (Refactor core)
  - Days 5-6: Phase 3 (PipelineWorker)
  - Day 7: Phase 4 (Testing)

- **Week 2:** Evaluation experiments
  - Create ground truth dataset
  - Run pipeline with 3 profiles
  - Measure accuracy metrics
  - Generate comparison tables/graphs

- **Week 3:** Thesis writing (draft)
  - Introduction & Related Work
  - Methodology & Architecture chapters
  - Implementation details
  - Evaluation results

- **Week 4:** Thesis finalization
  - Revisions based on advisor feedback
  - Proofreading and formatting
  - Abstract, acknowledgments
  - Final submission

---

## 🚀 READY TO START?

1. **Read MODULARITY_EXPLAINED.md** (20 min) - Understand WHY
2. **Open new Claude Code chat** - Get implementation help
3. **Paste the prompt from "Method 1" above** - Start Phase 1
4. **Follow the checklist** - Track your progress

**You've got this! The implementation guide has everything you need.** 💪

---

**Good luck with your modularity refactoring and thesis submission!** 🎓

---

**QUICK REFERENCE:**

| Document | Purpose | When to Use |
|----------|---------|-------------|
| MODULARITY_EXPLAINED.md | Conceptual understanding | Read first (20 min) |
| MODULARITY_IMPLEMENTATION_GUIDE.md | Complete technical guide | Reference during implementation |
| MODULARITY_QUICKSTART.md | Quick checklist | Track progress |

**Total time investment:** 10-14 hours
**Thesis benefit:** Significant improvement in architecture quality
**ROI:** Excellent - makes thesis much stronger

---
