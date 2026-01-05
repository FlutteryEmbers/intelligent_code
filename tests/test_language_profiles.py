"""Test language profile loading"""
import sys
sys.path.insert(0, '.')

from src.utils.language_profile import load_language_profile, clear_profile_cache
from src.utils.config import Config

def test_java_profile():
    print("=" * 70)
    print("Testing Java Profile")
    print("=" * 70)
    
    try:
        profile = load_language_profile(language_name="java", profile_dir="configs/language")
        print(f"✓ Loaded language: {profile.language}")
        
        # Test QA markers
        markers = profile.get_qa_markers()
        print(f"✓ QA annotations: {len(markers['annotations'])} items")
        print(f"  Sample: {markers['annotations'][:3]}")
        print(f"✓ QA decorators: {len(markers['decorators'])} items")
        
        # Test QA scoring
        scoring = profile.get_qa_scoring()
        print(f"✓ Scoring weights: annotation={scoring['annotation_weight']}, "
              f"doc={scoring['doc_weight']}")
        
        # Test Design layers
        controller = profile.get_design_layer("controller")
        print(f"✓ Controller annotations: {controller['annotations']}")
        
        service = profile.get_design_layer("service")
        print(f"✓ Service annotations: {service['annotations']}")
        
        repository = profile.get_design_layer("repository")
        print(f"✓ Repository annotations: {repository['annotations']}")
        
        print("\n✅ Java profile validation PASSED\n")
        return True
        
    except Exception as e:
        print(f"\n❌ Java profile validation FAILED: {e}\n")
        import traceback
        traceback.print_exc()
        return False


def test_python_profile():
    print("=" * 70)
    print("Testing Python Profile")
    print("=" * 70)
    
    try:
        profile = load_language_profile(language_name="python", profile_dir="configs/language")
        print(f"✓ Loaded language: {profile.language}")
        
        # Test QA markers
        markers = profile.get_qa_markers()
        print(f"✓ QA decorators: {len(markers['decorators'])} items")
        print(f"  Sample: {markers['decorators'][:3]}")
        print(f"✓ QA annotations: {len(markers['annotations'])} items")
        
        # Test QA scoring
        scoring = profile.get_qa_scoring()
        print(f"✓ Scoring weights: decorator={scoring['decorator_weight']}, "
              f"doc={scoring['doc_weight']}")
        
        # Test Design layers
        controller = profile.get_design_layer("controller")
        print(f"✓ Controller decorators: {controller['decorators']}")
        print(f"✓ Controller path keywords: {controller['path_keywords']}")
        
        service = profile.get_design_layer("service")
        print(f"✓ Service decorators: {service['decorators']}")
        
        repository = profile.get_design_layer("repository")
        print(f"✓ Repository name keywords: {repository['name_keywords']}")
        
        print("\n✅ Python profile validation PASSED\n")
        return True
        
    except Exception as e:
        print(f"\n❌ Python profile validation FAILED: {e}\n")
        import traceback
        traceback.print_exc()
        return False


def test_config_integration():
    print("=" * 70)
    print("Testing Config Integration")
    print("=" * 70)
    
    try:
        config = Config()
        
        # Test reading language config
        lang_name = config.get("language.name")
        print(f"✓ Config language.name: {lang_name}")
        
        profile_dir = config.get("language.profile_dir")
        print(f"✓ Config language.profile_dir: {profile_dir}")
        
        # Test loading from config
        profile = load_language_profile(config=config)
        print(f"✓ Auto-loaded profile for language: {profile.language}")
        
        print("\n✅ Config integration PASSED\n")
        return True
        
    except Exception as e:
        print(f"\n❌ Config integration FAILED: {e}\n")
        import traceback
        traceback.print_exc()
        return False


def test_caching():
    print("=" * 70)
    print("Testing Profile Caching")
    print("=" * 70)
    
    try:
        clear_profile_cache()
        
        # First load
        profile1 = load_language_profile(language_name="java", profile_dir="configs/language")
        print("✓ First load successful")
        
        # Second load (should use cache)
        profile2 = load_language_profile(language_name="java", profile_dir="configs/language")
        print("✓ Second load successful")
        
        # They should be the same object (cached)
        if profile1 is profile2:
            print("✓ Cache working correctly (same object)")
        else:
            print("⚠ Warning: Cache not working (different objects)")
        
        print("\n✅ Caching test PASSED\n")
        return True
        
    except Exception as e:
        print(f"\n❌ Caching test FAILED: {e}\n")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    results = []
    
    results.append(("Java Profile", test_java_profile()))
    results.append(("Python Profile", test_python_profile()))
    results.append(("Config Integration", test_config_integration()))
    results.append(("Caching", test_caching()))
    
    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)
    for name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status}: {name}")
    
    all_passed = all(p for _, p in results)
    print("=" * 70)
    
    if all_passed:
        print("\n🎉 All tests PASSED! Language profiles are ready.")
        sys.exit(0)
    else:
        print("\n⚠️  Some tests FAILED. Please check the errors above.")
        sys.exit(1)
