# Pipeline Architecture

## 📁 New Structure

```
src/pipeline/
├── __init__.py              # Package exports
├── orchestrator.py          # Pipeline coordinator (178 lines)
├── base_step.py             # Base class for steps (73 lines)
├── helpers.py               # Helper functions (95 lines)
└── steps/
    ├── __init__.py
    ├── parse.py             # Step 1: Parse Repository
    ├── auto_module.py       # Auto Module: Method Profiles & QA
    ├── qa_generation.py     # Step 2: QA Generation
    ├── design_generation.py # Step 3: Design Generation
    ├── validation.py        # Step 4: Validation
    ├── merge.py             # Step 5: Merge Samples
    ├── deduplication.py     # Step 6: Deduplication
    ├── secrets_scan.py      # Step 7: Secrets Scanning
    ├── split.py             # Step 8: Dataset Split
    └── export.py            # Step 9: Export to SFT
```

## 🎯 Key Improvements

### 1. **Separation of Concerns**
- Each step is an independent module
- Clear interfaces via `BaseStep` class
- Easy to test, modify, or disable individual steps

### 2. **Simplified main.py**
- **Before**: 905 lines
- **After**: 63 lines
- Only handles argument parsing and pipeline initialization

### 3. **Consistent Error Handling**
- All steps use `try/except` in `BaseStep.run()`
- Errors are logged and recorded in summary
- Pipeline continues even if a step fails

### 4. **Better Skip Logic**
- Each step implements `should_skip()` method
- Clear reasons for skipping (cache_hit, skip_flag, disabled, etc.)
- Logged in summary for debugging

### 5. **Modular Design**
```python
class MyStep(BaseStep):
    @property
    def name(self) -> str:
        return "my_step"
    
    @property
    def display_name(self) -> str:
        return "Step X: My Step"
    
    def should_skip(self) -> tuple[bool, str]:
        # Check if should skip
        return False, ""
    
    def execute(self) -> dict:
        # Do the work
        return {"status": "success"}
```

## 🔄 Migration Guide

### Old Code (main.py)
```python
# 905 lines of sequential code
if args.skip_parse and should_skip_parse(...):
    logger.info("Skipping parse")
else:
    logger.info("=" * 70)
    logger.info(" Step 1: Parsing Repository")
    try:
        # ... 50 lines of logic
    except Exception as e:
        logger.error(...)
```

### New Code
```python
# Step defined in src/pipeline/steps/parse.py
class ParseStep(BaseStep):
    def execute(self) -> dict:
        # ... 30 lines of logic (no boilerplate)

# Used in orchestrator.py
steps = [ParseStep(...), ...]
for step in steps:
    result = step.run()  # Handles logging, errors, skips
```

## 📊 File Comparison

| File | Old Lines | New Lines | Reduction |
|------|-----------|-----------|-----------|
| main.py | 905 | 63 | **93% ↓** |
| Total Code | 905 | ~800 (split) | More readable |

## 🚀 Usage

### Same as before
```bash
python main.py                    # Run full pipeline
python main.py --skip-qa          # Skip QA generation
python main.py --skip-parse       # Use cached symbols
```

### Adding a New Step
1. Create `src/pipeline/steps/my_step.py`
2. Inherit from `BaseStep`
3. Implement `name`, `display_name`, `execute()`
4. Add to `orchestrator.py` steps list

## 🔍 Debugging

### View Step Results
All step results are in `data/reports/pipeline_summary.json`:
```json
{
  "steps": {
    "parse": {"status": "success", "symbols_count": 150},
    "auto": {"status": "success", "method_profiles": 30},
    "validation": {"status": "skipped", "reason": "no_samples"}
  }
}
```

### Check Logs
Each step logs with its class name:
```
INFO - ParseStep - Parsed 150 symbols
INFO - AutoModuleStep - Generated 30 method profiles
```

## 📝 Notes

- Original main.py backed up to `main_old.py`
- All functionality preserved
- No breaking changes to CLI or config
- Tests should continue to work

## 🎨 Benefits

✅ **Readability**: Each step is self-contained  
✅ **Maintainability**: Easy to modify individual steps  
✅ **Testability**: Steps can be unit tested  
✅ **Extensibility**: Add new steps without touching others  
✅ **Debugging**: Clear step boundaries and logging  
✅ **Reusability**: Steps can be reused in different pipelines
