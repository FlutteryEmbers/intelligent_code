"""
Test refactored pipeline with language profiles
验证多语言支持和profile加载是否正常
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.utils.config import Config
from src.utils.language_profile import load_language_profile
from src.engine.qa_generator import QAGenerator
from src.engine.design_generator import DesignGenerator
from src.utils.logger import get_logger

logger = get_logger(__name__)


def test_java_profile():
    """Test Java language profile loading"""
    print("\n=== Testing Java Profile ===")
    
    # Force Java language
    config = Config()
    config.data['language'] = {'name': 'java', 'profile_dir': 'configs/language'}
    
    profile = load_language_profile(config=config)
    
    print(f"✓ Language: {profile.language}")
    print(f"✓ QA Markers: {len(profile.get_qa_markers())} annotations/decorators")
    print(f"✓ QA Scoring: {profile.get_qa_scoring()}")
    print(f"✓ Design Layers: {list(profile.layers.keys())}")
    
    # Test layer retrieval
    controller = profile.get_design_layer('controller')
    print(f"✓ Controller annotations: {controller['annotations']}")
    
    return True


def test_python_profile():
    """Test Python language profile loading"""
    print("\n=== Testing Python Profile ===")
    
    # Force Python language
    config = Config()
    config.data['language'] = {'name': 'python', 'profile_dir': 'configs/language'}
    
    profile = load_language_profile(config=config)
    
    print(f"✓ Language: {profile.language}")
    print(f"✓ QA Markers: {len(profile.get_qa_markers())} annotations/decorators")
    print(f"✓ QA Scoring: {profile.get_qa_scoring()}")
    print(f"✓ Design Layers: {list(profile.layers.keys())}")
    
    # Test layer retrieval
    service = profile.get_design_layer('service')
    print(f"✓ Service decorators: {service['decorators']}")
    
    return True


def test_qa_generator_java():
    """Test QA Generator with Java profile"""
    print("\n=== Testing QA Generator (Java) ===")
    
    config = Config()
    config.data['language'] = {'name': 'java', 'profile_dir': 'configs/language'}
    
    try:
        qa_gen = QAGenerator(config=config)
        print(f"✓ QA Generator initialized")
        print(f"✓ Profile language: {qa_gen.profile.language}")
        print(f"✓ Top-K: {qa_gen.top_k}")
        return True
    except Exception as e:
        print(f"✗ QA Generator failed: {e}")
        return False


def test_design_generator_java():
    """Test Design Generator with Java profile"""
    print("\n=== Testing Design Generator (Java) ===")
    
    config = Config()
    config.data['language'] = {'name': 'java', 'profile_dir': 'configs/language'}
    
    try:
        design_gen = DesignGenerator(config=config)
        print(f"✓ Design Generator initialized")
        print(f"✓ Profile language: {design_gen.profile.language}")
        print(f"✓ Top-K context: {design_gen.top_k_context}")
        return True
    except Exception as e:
        print(f"✗ Design Generator failed: {e}")
        return False


def test_qa_generator_python():
    """Test QA Generator with Python profile"""
    print("\n=== Testing QA Generator (Python) ===")
    
    config = Config()
    config.data['language'] = {'name': 'python', 'profile_dir': 'configs/language'}
    
    try:
        qa_gen = QAGenerator(config=config)
        print(f"✓ QA Generator initialized")
        print(f"✓ Profile language: {qa_gen.profile.language}")
        return True
    except Exception as e:
        print(f"✗ QA Generator failed: {e}")
        return False


def test_design_generator_python():
    """Test Design Generator with Python profile"""
    print("\n=== Testing Design Generator (Python) ===")
    
    config = Config()
    config.data['language'] = {'name': 'python', 'profile_dir': 'configs/language'}
    
    try:
        design_gen = DesignGenerator(config=config)
        print(f"✓ Design Generator initialized")
        print(f"✓ Profile language: {design_gen.profile.language}")
        return True
    except Exception as e:
        print(f"✗ Design Generator failed: {e}")
        return False


if __name__ == '__main__':
    print("=" * 60)
    print("Testing Refactored Pipeline with Language Profiles")
    print("=" * 60)
    
    results = []
    
    # Test profiles
    results.append(("Java Profile", test_java_profile()))
    results.append(("Python Profile", test_python_profile()))
    
    # Test generators with Java
    results.append(("QA Generator (Java)", test_qa_generator_java()))
    results.append(("Design Generator (Java)", test_design_generator_java()))
    
    # Test generators with Python
    results.append(("QA Generator (Python)", test_qa_generator_python()))
    results.append(("Design Generator (Python)", test_design_generator_python()))
    
    # Summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status}: {name}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 All tests passed! Refactoring successful!")
        sys.exit(0)
    else:
        print(f"\n⚠️  {total - passed} test(s) failed")
        sys.exit(1)
