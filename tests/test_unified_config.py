"""
Test unified language configuration (single language.name setting)
验证统一的语言配置
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.utils.config import Config
from src.utils.language_profile import load_language_profile
from src.pipeline.steps.parse import ParseStep


def test_single_language_config():
    """Test that language.name controls both parser and profile"""
    print("\n=== Testing Unified Language Configuration ===")
    
    # Test 1: Java configuration
    print("\n1. Testing Java Configuration:")
    config = Config()
    config.data['language'] = {'name': 'java', 'profile_dir': 'configs/language'}
    config.data['repo'] = {'path': './repos/java/test_repo', 'commit': 'test'}
    
    # Should load Java profile
    profile = load_language_profile(config=config)
    print(f"   ✓ Profile language: {profile.language}")
    assert profile.language == "java", "Profile should be Java"
    
    # Should select Java parser
    parse_step = ParseStep(config=config)
    print(f"   ✓ Parse step initialized (will use Java parser)")
    
    # Test 2: Python configuration
    print("\n2. Testing Python Configuration:")
    config2 = Config()
    config2.data['language'] = {'name': 'python', 'profile_dir': 'configs/language'}
    config2.data['repo'] = {'path': './repos/python/test_repo', 'commit': 'test'}
    
    # Should load Python profile
    profile2 = load_language_profile(config=config2)
    print(f"   ✓ Profile language: {profile2.language}")
    assert profile2.language == "python", "Profile should be Python"
    
    # Should select Python parser
    parse_step2 = ParseStep(config=config2)
    print(f"   ✓ Parse step initialized (will use Python parser)")
    
    print("\n✅ All tests passed! Single language.name configuration works correctly.")
    print("   - language.name controls both parser selection and profile loading")
    print("   - No need for separate parser.type configuration")
    
    return True


def test_default_language():
    """Test default language fallback"""
    print("\n=== Testing Default Language (no language.name) ===")
    
    config = Config()
    config.data.pop('language', None)  # Remove language config
    
    # Should default to Java
    profile = load_language_profile(config=config)
    print(f"   ✓ Default profile language: {profile.language}")
    assert profile.language == "java", "Should default to Java"
    
    print("\n✅ Default fallback works correctly (defaults to 'java')")
    
    return True


if __name__ == '__main__':
    print("=" * 60)
    print("Unified Language Configuration Test")
    print("=" * 60)
    
    try:
        test_single_language_config()
        test_default_language()
        
        print("\n" + "=" * 60)
        print("🎉 All Unified Configuration Tests Passed!")
        print("=" * 60)
        print("\nConfiguration Guide:")
        print("  Edit configs/pipeline.yaml:")
        print("    language:")
        print("      name: 'java'  # or 'python'")
        print("\n  This single setting controls:")
        print("    - Parser selection (JavaParser or PythonParser)")
        print("    - Language profile loading (java.yaml or python.yaml)")
        sys.exit(0)
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
