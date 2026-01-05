"""
测试 LLM 是否能正确生成 requirement schema
"""
import json
from src.engine.llm_client import LLMClient
from src.utils.config import Config
from langchain_core.messages import SystemMessage, HumanMessage

# 初始化
config = Config()
llm_client = LLMClient()

print(f"LLM Config: model={llm_client.model}, temperature={llm_client.temperature}")
print(f"Base URL: {llm_client.base_url}")
print("-" * 80)

# 简化的 system prompt
system_prompt = """You are a JSON generation machine. Output ONLY this JSON structure:

{
  "requirements": [
    {
      "id": "REQ-AUTO-001",
      "goal": "Implement caching for product queries",
      "constraints": ["Use Redis", "TTL 15 minutes"],
      "acceptance_criteria": ["Cache hit rate > 90%", "Response time < 50ms"],
      "non_goals": ["Distributed cache"],
      "evidence_refs": [
        {"symbol_id": "example:Example:1", "file_path": "Example.java", "start_line": 1, "end_line": 10, "source_hash": "abc123"}
      ]
    }
  ]
}

FORBIDDEN field names: name, description, test_cases, expected_behavior, file_path (at top level), line_range
REQUIRED field names: id, goal, constraints, acceptance_criteria, non_goals, evidence_refs

Output ONLY valid JSON, start with { and end with }"""

# 简化的 user prompt
user_prompt = """Generate 1 requirement for rate limiting.

Evidence Pool:
{"symbol_id": "AuthController:login:45", "file_path": "AuthController.java", "start_line": 45, "end_line": 67, "source_hash": "xyz789"}

Output JSON now:"""

print("Sending to LLM...")
print("=" * 80)

messages = [
    SystemMessage(content=system_prompt),
    HumanMessage(content=user_prompt)
]

response = llm_client.llm.invoke(messages)
output = response.content

print("LLM Response:")
print(output)
print("=" * 80)

# 尝试解析
try:
    # 清理输出
    import re
    cleaned = output.strip()
    cleaned = re.sub(r'```json\s*', '', cleaned)
    cleaned = re.sub(r'```\s*', '', cleaned)
    
    data = json.loads(cleaned)
    print("\n✅ JSON parsed successfully!")
    print(json.dumps(data, indent=2, ensure_ascii=False))
    
    # 检查 schema
    if 'requirements' in data and data['requirements']:
        req = data['requirements'][0]
        print(f"\nActual fields: {list(req.keys())}")
        
        required_fields = ['id', 'goal', 'constraints', 'acceptance_criteria', 'non_goals', 'evidence_refs']
        missing = [f for f in required_fields if f not in req]
        wrong = [k for k in req.keys() if k not in required_fields]
        
        if missing:
            print(f"❌ Missing fields: {missing}")
        if wrong:
            print(f"❌ Unexpected fields: {wrong}")
        if not missing and not wrong:
            print("✅ Schema is correct!")
    
except json.JSONDecodeError as e:
    print(f"\n❌ JSON parse error: {e}")
    print(f"Error at position {e.pos}")
except Exception as e:
    print(f"\n❌ Error: {e}")
