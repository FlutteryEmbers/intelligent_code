import hashlib
from datetime import datetime, timezone
from pydantic import BaseModel, Field

def sha256_text(text: str) -> str:
    """计算文本的 SHA256 哈希值"""
    return hashlib.sha256(text.encode('utf-8')).hexdigest()

def now_iso() -> str:
    """返回当前 UTC 时间的 ISO 格式字符串"""
    return datetime.now(timezone.utc).isoformat()

class Annotation(BaseModel):
    """Java 注解模型"""
    name: str = Field(..., description="注解名称，如 @Override")
    arguments: dict | None = Field(default=None, description="注解参数字典")
    raw_text: str = Field(..., description="注解原始文本")

    class Config:
        frozen = False
