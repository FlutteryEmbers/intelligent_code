"""
Java Parser 测试脚本
"""
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.parser import JavaParser, get_repo_commit
from src.utils import config, get_logger

logger = get_logger(__name__)


def test_parse_simple_java():
    """测试解析简单的 Java 代码片段"""
    print("\n" + "=" * 70)
    print(" 测试 1: 解析简单的 Java 代码")
    print("=" * 70)
    
    # 创建测试文件
    test_dir = Path("data/test_java_repo")
    test_dir.mkdir(parents=True, exist_ok=True)
    
    test_file = test_dir / "Example.java"
    test_code = '''package com.example.demo;

import org.springframework.web.bind.annotation.*;

/**
 * 示例控制器
 */
@RestController
@RequestMapping("/api")
public class Example {
    
    /**
     * 获取问候消息
     * @param name 名称
     * @return 问候消息
     */
    @GetMapping("/hello")
    public String hello(@RequestParam String name) {
        return "Hello, " + name;
    }
    
    /**
     * 创建用户
     */
    @PostMapping("/user")
    @Transactional
    public void createUser(@RequestBody User user) {
        // 创建用户逻辑
        System.out.println("Creating user: " + user.getName());
    }
}
'''
    
    with open(test_file, 'w', encoding='utf-8') as f:
        f.write(test_code)
    
    print(f"✓ 创建测试文件: {test_file}")
    
    # 解析
    parser = JavaParser()
    commit = "test_commit_123"
    
    print(f"✓ 开始解析...")
    symbols = parser.parse_repo(str(test_dir), commit)
    
    print(f"\n解析结果：")
    print(f"  - 总符号数: {len(symbols)}")
    
    for i, symbol in enumerate(symbols, 1):
        print(f"\n  符号 {i}:")
        print(f"    - 类型: {symbol.symbol_type}")
        print(f"    - 名称: {symbol.name}")
        print(f"    - 完全限定名: {symbol.qualified_name}")
        print(f"    - 位置: {symbol.file_path}:{symbol.start_line}-{symbol.end_line}")
        print(f"    - 注解数量: {len(symbol.annotations)}")
        
        if symbol.annotations:
            for ann in symbol.annotations:
                print(f"      • @{ann.name}", end="")
                if ann.arguments:
                    print(f"({ann.arguments})", end="")
                print()
        
        if symbol.doc:
            print(f"    - JavaDoc: {symbol.doc[:50]}...")
        
        print(f"    - 源码长度: {len(symbol.source)} 字符")
        if symbol.metadata.get('truncated'):
            print(f"    - ⚠️  已截断（原始: {symbol.metadata['original_chars']} 字符）")
    
    print(f"\n✓ 测试完成")
    print(f"  - 符号已保存到: data/raw/extracted/symbols.jsonl")
    print(f"  - 元数据已保存到: data/raw/repo_meta/repo_meta.json")
    
    return len(symbols) > 0


def test_parse_real_repo():
    """测试解析真实的 Java 仓库"""
    print("\n" + "=" * 70)
    print(" 测试 2: 解析真实 Java 仓库")
    print("=" * 70)
    
    # 从配置读取仓库路径
    repo_path = config.repo_path
    
    if not repo_path or repo_path == "path/to/your/java/repo":
        print("⚠️  跳过（请在 configs/pipeline.yaml 中配置 repo.path）")
        return True
    
    repo_path_obj = Path(repo_path)
    if not repo_path_obj.exists():
        print(f"⚠️  跳过（仓库路径不存在: {repo_path}）")
        return True
    
    print(f"仓库路径: {repo_path}")
    
    # 获取 commit
    commit = get_repo_commit(repo_path)
    print(f"Commit: {commit}")
    
    # 解析
    parser = JavaParser()
    
    print(f"\n开始解析（这可能需要几分钟）...")
    symbols = parser.parse_repo(repo_path, commit)
    
    print(f"\n解析完成！")
    print(f"  - 总符号数: {len(symbols)}")
    
    # 统计
    from collections import Counter
    
    symbol_types = Counter(s.symbol_type for s in symbols)
    print(f"\n符号类型分布：")
    for stype, count in symbol_types.items():
        print(f"  - {stype}: {count}")
    
    # 统计注解
    all_annotations = []
    for s in symbols:
        all_annotations.extend([a.name for a in s.annotations])
    
    if all_annotations:
        ann_counter = Counter(all_annotations)
        print(f"\n最常见的注解（Top 10）：")
        for ann, count in ann_counter.most_common(10):
            print(f"  - @{ann}: {count}")
    
    # 统计截断
    truncated_count = sum(1 for s in symbols if s.metadata.get('truncated'))
    if truncated_count > 0:
        print(f"\n⚠️  {truncated_count} 个符号因长度超限被截断")
    
    print(f"\n✓ 测试完成")
    print(f"  - 符号已保存到: data/raw/extracted/symbols.jsonl")
    print(f"  - 元数据已保存到: data/raw/repo_meta/repo_meta.json")
    print(f"  - 报告已保存到: data/reports/parsing_report.json")
    
    return True


def main():
    """主测试函数"""
    print("\n" + "=" * 70)
    print(" JavaParser 功能测试")
    print("=" * 70)
    
    try:
        # 测试 1: 简单代码
        success1 = test_parse_simple_java()
        
        # 测试 2: 真实仓库（可选）
        success2 = test_parse_real_repo()
        
        if success1 and success2:
            print("\n" + "=" * 70)
            print(" ✓ 所有测试通过！")
            print("=" * 70)
            return True
        else:
            print("\n" + "=" * 70)
            print(" ✗ 部分测试失败")
            print("=" * 70)
            return False
            
    except Exception as e:
        print(f"\n✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
