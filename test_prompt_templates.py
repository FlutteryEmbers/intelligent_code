#!/usr/bin/env python
"""测试prompt模板加载功能"""
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.engine.qa_generator import load_prompt_template, QAGenerator
from src.engine.design_generator import DesignGenerator

def test_load_templates():
    """测试模板文件加载"""
    print("=" * 60)
    print("测试 Prompt 模板加载")
    print("=" * 60)
    
    templates = [
        "qa_system_prompt.txt",
        "qa_user_prompt.txt",
        "design_system_prompt.txt",
        "design_user_prompt.txt"
    ]
    
    for template_name in templates:
        try:
            content = load_prompt_template(template_name)
            print(f"\n✓ {template_name}")
            print(f"  长度: {len(content)} 字符")
            print(f"  前100字符: {content[:100]}...")
        except Exception as e:
            print(f"\n✗ {template_name}")
            print(f"  错误: {e}")
            return False
    
    return True

def test_generator_init():
    """测试生成器初始化"""
    print("\n" + "=" * 60)
    print("测试生成器初始化")
    print("=" * 60)
    
    try:
        print("\n初始化 QAGenerator...")
        qa_gen = QAGenerator()
        print(f"✓ QAGenerator 初始化成功")
        print(f"  System prompt 长度: {len(qa_gen.system_prompt_template)} 字符")
        print(f"  User prompt 长度: {len(qa_gen.user_prompt_template)} 字符")
    except Exception as e:
        print(f"✗ QAGenerator 初始化失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    try:
        print("\n初始化 DesignGenerator...")
        design_gen = DesignGenerator()
        print(f"✓ DesignGenerator 初始化成功")
        print(f"  System prompt 长度: {len(design_gen.system_prompt_template)} 字符")
        print(f"  User prompt 长度: {len(design_gen.user_prompt_template)} 字符")
    except Exception as e:
        print(f"✗ DesignGenerator 初始化失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    return True

if __name__ == '__main__':
    print("\n开始测试...\n")
    
    success = True
    success = test_load_templates() and success
    success = test_generator_init() and success
    
    print("\n" + "=" * 60)
    if success:
        print("✓ 所有测试通过")
        sys.exit(0)
    else:
        print("✗ 部分测试失败")
        sys.exit(1)
