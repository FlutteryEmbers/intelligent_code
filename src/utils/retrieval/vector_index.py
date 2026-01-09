"""
向量索引工具 - 用于 demo 模块的语义检索

使用 Ollama 的 embedding API 进行向量化，纯 Python 实现余弦相似度检索。
"""
import json
import math
from pathlib import Path
from typing import List, Tuple

try:
    import ollama
except ImportError:
    raise ImportError("ollama package not found. Please install: pip install ollama")

from src.utils.core.logger import get_logger

logger = get_logger(__name__)


def cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    """计算两个向量的余弦相似度
    
    Args:
        vec1: 向量1
        vec2: 向量2
        
    Returns:
        float: 余弦相似度 [-1, 1]
    """
    if len(vec1) != len(vec2):
        raise ValueError(f"Vector dimensions mismatch: {len(vec1)} vs {len(vec2)}")
    
    dot_product = sum(a * b for a, b in zip(vec1, vec2))
    norm1 = math.sqrt(sum(a * a for a in vec1))
    norm2 = math.sqrt(sum(b * b for b in vec2))
    
    if norm1 == 0 or norm2 == 0:
        return 0.0
    
    return dot_product / (norm1 * norm2)


def build_embeddings(
    profiles_jsonl: Path,
    embeddings_jsonl: Path,
    embedding_model: str = "nomic-embed-text",
    repo_commit: str = "UNKNOWN_COMMIT"
) -> int:
    """为方法 profiles 构建向量索引
    
    Args:
        profiles_jsonl: 输入的 method profiles JSONL 文件
        embeddings_jsonl: 输出的 embeddings JSONL 文件
        embedding_model: Ollama embedding 模型名称
        repo_commit: 仓库 commit hash
        
    Returns:
        int: 成功处理的条目数
    """
    logger.info(f"Building embeddings for {profiles_jsonl}")
    logger.info(f"Using embedding model: {embedding_model}")
    
    profiles_path = Path(profiles_jsonl)
    if not profiles_path.exists():
        logger.error(f"Profiles file not found: {profiles_path}")
        return 0
    
    # 读取所有 profiles
    profiles = []
    with open(profiles_path, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                profiles.append(json.loads(line))
    
    logger.info(f"Loaded {len(profiles)} profiles")
    
    # 为每个 profile 生成 embedding
    embeddings_path = Path(embeddings_jsonl)
    embeddings_path.parent.mkdir(parents=True, exist_ok=True)
    
    success_count = 0
    with open(embeddings_path, 'w', encoding='utf-8') as f:
        for i, profile in enumerate(profiles, 1):
            try:
                # 构造用于 embedding 的文本
                text = _build_embedding_text(profile)
                
                # 调用 Ollama embedding API
                logger.debug(f"Generating embedding for {profile['symbol_id']} ({i}/{len(profiles)})")
                response = ollama.embeddings(
                    model=embedding_model,
                    prompt=text
                )
                
                embedding = response['embedding']
                
                # 写入 embedding
                embedding_entry = {
                    'symbol_id': profile['symbol_id'],
                    'file_path': profile['file_path'],
                    'qualified_name': profile['qualified_name'],
                    'embedding': embedding,
                    'text': text[:500],  # 保留前500字符用于调试
                    'repo_commit': repo_commit
                }
                
                f.write(json.dumps(embedding_entry, ensure_ascii=False) + '\n')
                success_count += 1
                
                if i % 10 == 0:
                    logger.info(f"Processed {i}/{len(profiles)} profiles")
                    
            except Exception as e:
                logger.error(f"Failed to generate embedding for {profile.get('symbol_id', 'unknown')}: {e}")
                continue
    
    logger.info(f"Successfully generated {success_count} embeddings")
    return success_count


def _build_embedding_text(profile: dict) -> str:
    """构造用于 embedding 的文本
    
    Args:
        profile: MethodProfile 字典
        
    Returns:
        str: 组合的文本
    """
    parts = []
    
    # 方法名和摘要
    parts.append(f"{profile.get('qualified_name', '')}")
    parts.append(profile.get('summary', ''))
    
    # 业务规则
    if profile.get('business_rules'):
        parts.append("业务规则: " + "; ".join(profile['business_rules']))
    
    # 标签
    if profile.get('tags'):
        parts.append("标签: " + ", ".join(profile['tags']))
    
    return " | ".join(filter(None, parts))


def search(
    query_text: str,
    embeddings_jsonl: Path,
    embedding_model: str = "nomic-embed-text",
    top_k: int = 6
) -> List[Tuple[str, float]]:
    """检索最相关的 Top-K 方法
    
    Args:
        query_text: 查询文本（问题）
        embeddings_jsonl: embeddings JSONL 文件
        embedding_model: Ollama embedding 模型名称
        top_k: 返回的结果数量
        
    Returns:
        List[Tuple[str, float]]: (symbol_id, similarity_score) 列表，按相似度降序
    """
    logger.debug(f"Searching for: {query_text[:100]}...")
    
    embeddings_path = Path(embeddings_jsonl)
    if not embeddings_path.exists():
        logger.error(f"Embeddings file not found: {embeddings_path}")
        return []
    
    # 生成查询向量
    try:
        response = ollama.embeddings(
            model=embedding_model,
            prompt=query_text
        )
        query_embedding = response['embedding']
    except Exception as e:
        logger.error(f"Failed to generate query embedding: {e}")
        return []
    
    # 读取所有 embeddings 并计算相似度
    similarities = []
    with open(embeddings_path, 'r', encoding='utf-8') as f:
        for line in f:
            if not line.strip():
                continue
            
            try:
                entry = json.loads(line)
                symbol_id = entry['symbol_id']
                embedding = entry['embedding']
                
                # 计算余弦相似度
                similarity = cosine_similarity(query_embedding, embedding)
                similarities.append((symbol_id, similarity))
                
            except Exception as e:
                logger.warning(f"Failed to process embedding entry: {e}")
                continue
    
    # 按相似度降序排序并返回 Top-K
    similarities.sort(key=lambda x: x[1], reverse=True)
    top_results = similarities[:top_k]
    
    logger.debug(f"Found {len(top_results)} results")
    for symbol_id, score in top_results[:3]:
        logger.debug(f"  - {symbol_id}: {score:.4f}")
    
    return top_results


# ==================== 自测代码 ====================
if __name__ == '__main__':
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
    
    # 测试余弦相似度
    vec1 = [1.0, 0.0, 0.0]
    vec2 = [1.0, 0.0, 0.0]
    vec3 = [0.0, 1.0, 0.0]
    
    print(f"cosine_similarity(vec1, vec2) = {cosine_similarity(vec1, vec2)}")  # 应该为 1.0
    print(f"cosine_similarity(vec1, vec3) = {cosine_similarity(vec1, vec3)}")  # 应该为 0.0
    
    print("\nVector index module loaded successfully!")
