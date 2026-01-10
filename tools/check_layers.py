
import json
from pathlib import Path
from src.utils.generation.language_profile import load_language_profile
from src.utils.core.config import Config

def check_layers():
    symbols_path = Path("data/raw/extracted/symbols.jsonl")
    if not symbols_path.exists():
        print("No symbols.jsonl")
        return

    config = Config()
    profile = load_language_profile(config)
    
    counts = {'controller': 0, 'service': 0, 'repository': 0, 'other': 0}
    with open(symbols_path, 'r', encoding='utf-8') as f:
        for line in f:
            s_dict = json.loads(line)
            # Mock CodeSymbol object for profile method (as it expects object with attrs)
            class MockSymbol:
                def __init__(self, d):
                    self.annotations = [] # mock
                    self.name = d['name']
                    self.qualified_name = d['qualified_name']
                    self.file_path = d['file_path']
                    # mock annotations object list if needed
                    self.annotations = [type('Ann', (), {'name': a['name']}) for a in d.get('annotations', [])]
            
            s = MockSymbol(s_dict)
            layer = profile.get_layer(s)
            if layer:
                counts[layer] += 1
            else:
                counts['other'] += 1
                
    print(f"Layer distribution: {counts}")

if __name__ == "__main__":
    check_layers()
