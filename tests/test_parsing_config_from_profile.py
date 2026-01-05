"""
Test parsing configuration from language profiles
验证解析配置从language profile加载
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.utils.config import Config
from src.utils.language_profile import load_language_profile
from src.parser.java_parser import JavaParser
from src.parser.python_parser import PythonParser


def test_java_parsing_config():
    """Test Java parser loads config from profile"""
    print("\n=== Testing Java Parsing Configuration ===")
    
    config = Config()
    config.data['language'] = {'name': 'java', 'profile_dir': 'configs/language'}
    
    # Load profile directly
    profile = load_language_profile(config=config)
    print(f"✓ Profile language: {profile.language}")
    
    # Check parsing config in profile
    parsing_config = profile.get_parsing_config()
    print(f"✓ File extensions: {parsing_config['file_extensions']}")
    print(f"✓ Max chars: {parsing_config['max_chars_per_symbol']}")
    print(f"✓ Ignore paths: {len(parsing_config['ignore_paths'])} patterns")
    
    assert '.java' in parsing_config['file_extensions'], "Should have .java extension"
    assert 'target' in parsing_config['ignore_paths'], "Should ignore Maven target dir"
    assert parsing_config['max_chars_per_symbol'] == 12000, "Should be 12000 for Java"
    
    # Create parser and verify it uses profile config
    parser = JavaParser(config)
    print(f"✓ Parser max_chars: {parser.max_chars_per_symbol}")
    print(f"✓ Parser file_extensions: {parser.file_extensions}")
    print(f"✓ Parser ignore_paths: {len(parser.ignore_paths)} patterns")
    
    assert parser.max_chars_per_symbol == 12000
    assert '.java' in parser.file_extensions
    assert 'target' in parser.ignore_paths
    
    print("✅ Java parsing config loaded from profile successfully!")
    return True


def test_python_parsing_config():
    """Test Python parser loads config from profile"""
    print("\n=== Testing Python Parsing Configuration ===")
    
    config = Config()
    config.data['language'] = {'name': 'python', 'profile_dir': 'configs/language'}
    
    # Load profile directly
    profile = load_language_profile(config=config)
    print(f"✓ Profile language: {profile.language}")
    
    # Check parsing config in profile
    parsing_config = profile.get_parsing_config()
    print(f"✓ File extensions: {parsing_config['file_extensions']}")
    print(f"✓ Max chars: {parsing_config['max_chars_per_symbol']}")
    print(f"✓ Ignore paths: {len(parsing_config['ignore_paths'])} patterns")
    
    assert '.py' in parsing_config['file_extensions'], "Should have .py extension"
    assert 'venv' in parsing_config['ignore_paths'], "Should ignore venv"
    assert '__pycache__' in parsing_config['ignore_paths'], "Should ignore __pycache__"
    assert parsing_config['max_chars_per_symbol'] == 8000, "Should be 8000 for Python"
    
    # Create parser and verify it uses profile config
    parser = PythonParser(config)
    print(f"✓ Parser max_chars: {parser.max_chars_per_symbol}")
    print(f"✓ Parser file_extensions: {parser.file_extensions}")
    print(f"✓ Parser ignore_paths: {len(parser.ignore_paths)} patterns")
    
    assert parser.max_chars_per_symbol == 8000
    assert '.py' in parser.file_extensions
    assert 'venv' in parser.ignore_paths
    
    print("✅ Python parsing config loaded from profile successfully!")
    return True


def test_config_override():
    """Test that pipeline.yaml can override profile defaults"""
    print("\n=== Testing Configuration Override ===")
    
    config = Config()
    config.data['language'] = {'name': 'java', 'profile_dir': 'configs/language'}
    
    # Add override in pipeline config
    config.data['parser'] = {
        'max_chars_per_symbol': 20000,  # Override profile's 12000
        'include_private': True          # Override profile's False
    }
    config.data['filter'] = {
        'ignore_paths': ['custom_ignore']  # Should merge with profile
    }
    
    parser = JavaParser(config)
    
    print(f"✓ Max chars overridden: {parser.max_chars_per_symbol} (expected 20000)")
    print(f"✓ Include private overridden: {parser.include_private} (expected True)")
    print(f"✓ Ignore paths merged: {'custom_ignore' in parser.ignore_paths}")
    print(f"✓ Profile ignores preserved: {'target' in parser.ignore_paths}")
    
    assert parser.max_chars_per_symbol == 20000, "Should use override value"
    assert parser.include_private == True, "Should use override value"
    assert 'custom_ignore' in parser.ignore_paths, "Should add custom ignore"
    assert 'target' in parser.ignore_paths, "Should keep profile ignores"
    
    print("✅ Configuration override works correctly!")
    return True


def test_language_switching():
    """Test switching language changes parsing config"""
    print("\n=== Testing Language Switching ===")
    
    # Java config
    java_config = Config()
    java_config.data['language'] = {'name': 'java', 'profile_dir': 'configs/language'}
    java_parser = JavaParser(java_config)
    
    # Python config
    python_config = Config()
    python_config.data['language'] = {'name': 'python', 'profile_dir': 'configs/language'}
    python_parser = PythonParser(python_config)
    
    # Compare
    print(f"✓ Java extensions: {java_parser.file_extensions}")
    print(f"✓ Python extensions: {python_parser.file_extensions}")
    print(f"✓ Java max_chars: {java_parser.max_chars_per_symbol}")
    print(f"✓ Python max_chars: {python_parser.max_chars_per_symbol}")
    
    assert '.java' in java_parser.file_extensions
    assert '.py' in python_parser.file_extensions
    assert java_parser.max_chars_per_symbol != python_parser.max_chars_per_symbol
    
    # Check language-specific ignores
    java_has_target = 'target' in java_parser.ignore_paths
    python_has_venv = 'venv' in python_parser.ignore_paths
    
    print(f"✓ Java ignores 'target': {java_has_target}")
    print(f"✓ Python ignores 'venv': {python_has_venv}")
    
    assert java_has_target, "Java should ignore Maven target"
    assert python_has_venv, "Python should ignore venv"
    
    print("✅ Language switching correctly changes parsing config!")
    return True


if __name__ == '__main__':
    print("=" * 70)
    print("Testing Parsing Configuration from Language Profiles")
    print("=" * 70)
    
    results = []
    
    try:
        results.append(("Java Parsing Config", test_java_parsing_config()))
        results.append(("Python Parsing Config", test_python_parsing_config()))
        results.append(("Config Override", test_config_override()))
        results.append(("Language Switching", test_language_switching()))
        
        # Summary
        print("\n" + "=" * 70)
        print("Test Summary")
        print("=" * 70)
        
        passed = sum(1 for _, result in results if result)
        total = len(results)
        
        for name, result in results:
            status = "✓ PASS" if result else "✗ FAIL"
            print(f"{status}: {name}")
        
        print(f"\nTotal: {passed}/{total} tests passed")
        
        if passed == total:
            print("\n🎉 All tests passed! Parsing config binds to language correctly!")
            print("\nKey Benefits:")
            print("  ✓ Switching language.name auto-updates file extensions")
            print("  ✓ Language-specific ignore patterns (target vs venv)")
            print("  ✓ Different max_chars defaults per language")
            print("  ✓ Pipeline.yaml can still override for project needs")
            sys.exit(0)
        else:
            print(f"\n⚠️  {total - passed} test(s) failed")
            sys.exit(1)
            
    except Exception as e:
        print(f"\n❌ Test execution failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
