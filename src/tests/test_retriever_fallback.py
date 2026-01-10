
import unittest
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# Mock missing dependencies BEFORE importing application code
import types
# Helper to mock a package and its submodules
def mock_module(name):
    m = types.ModuleType(name)
    sys.modules[name] = m
    return m

mock_module("langchain_openai").ChatOpenAI = MagicMock()
lc_core = mock_module("langchain_core")
mock_module("langchain_core.messages").SystemMessage = MagicMock()
sys.modules["langchain_core.messages"].HumanMessage = MagicMock()
mock_module("langchain_core.output_parsers").PydanticOutputParser = MagicMock()
mock_module("langchain_core.prompts").ChatPromptTemplate = MagicMock()
sys.modules["langchain_core.prompts"].HumanMessagePromptTemplate = MagicMock()
mock_module("ollama")

from src.schemas import CodeSymbol
from src.utils.retrieval.keyword import keyword_search
# Now safe to import, even if it triggers src.engine.__init__
from src.engine.rag.retriever import Retriever

class TestRetrieverFallback(unittest.TestCase):
    
    def setUp(self):
        # Create dummy symbols
        self.s1 = CodeSymbol(
            symbol_id="file1:Service:1",
            name="UserService", # Name match candidate
            qualified_name="com.example.UserService",
            file_path="src/main/java/com/example/UserService.java",
            language="java",
            symbol_type="class",
            start_line=1, end_line=10,
            source="public class UserService { public void login() {} }",
            source_hash="hash1",
            repo_commit="test_commit"
        )
        self.s2 = CodeSymbol(
            symbol_id="file2:Controller:1",
            name="UserController",
            qualified_name="com.example.UserController",
            file_path="src/main/java/com/example/UserController.java",
            language="java",
            symbol_type="class",
            start_line=1, end_line=10,
            source="public class UserController { // uses service }",
            source_hash="hash2",
            repo_commit="test_commit"
        )
        self.s3 = CodeSymbol(
            symbol_id="file3:Util:1",
            name="StringUtils",
            qualified_name="com.example.StringUtils",
            file_path="src/main/java/com/example/StringUtils.java",
            language="java",
            symbol_type="class",
            start_line=1, end_line=10,
            source="public class StringUtils { }",
            source_hash="hash3",
            repo_commit="test_commit"
        )
        self.all_symbols = [self.s1, self.s2, self.s3]

    def test_keyword_search_ranking(self):
        # Query matching Service
        query = "login service"
        results = keyword_search(query, self.all_symbols, top_k=2)
        
        # Expect UserService first (name match + source match 'login')
        # Expect UserController second (source match 'service')
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0].name, "UserService")
        
    def test_retriever_fallback_usage(self):
        # Mock Config and Profile
        mock_config = MagicMock()
        def config_get_side_effect(key, default=None):
            if key == 'artifacts.method_embeddings_jsonl':
                return "non_existent_embeddings.jsonl"
            return default
        mock_config.get.side_effect = config_get_side_effect
        
        mock_profile = MagicMock()
        # Mock balancing to do nothing or simple filter
        mock_profile.get_layer.return_value = "other"
        mock_profile.filter_by_layer.return_value = []
        
        retriever = Retriever(mock_config, mock_profile)
        
        # Ensure embeddings path doesn't exist
        with patch('pathlib.Path.exists', return_value=False):
            # Patch keyword_search to track calls
            with patch('src.engine.rag.retriever.keyword_search') as mock_kw:
                mock_kw.return_value = [self.s1]
                
                results = retriever.retrieve_relevant_symbols("login", self.all_symbols)
                
                # Check if keyword_search was called
                args, kwargs = mock_kw.call_args
                self.assertEqual(kwargs['query'], "login") # query
                self.assertEqual(len(results), 1)

    def test_layer_balancing_uses_keyword_search(self):
        mock_config = MagicMock()
        mock_config.get.side_effect = lambda k, d=None: d # default
        
        mock_profile = MagicMock()
        # Assume retrieval found nothing initially (to force balancing)
        
        # Setup specific layer behavior
        def get_layer_side_effect(s):
            return "unknown" 
        mock_profile.get_layer.side_effect = get_layer_side_effect
        
        # Assume we need a 'service' layer
        def filter_by_layer_side_effect(candidates, layer):
            if layer == 'service':
                return [self.s1, self.s3] # s1 is UserService, s3 is StringUtils(dummy)
            return []
        mock_profile.filter_by_layer.side_effect = filter_by_layer_side_effect
        mock_profile.profile_data = {} # for kw search
        
        retriever = Retriever(mock_config, mock_profile)
        retriever.embeddings_path = Path("non_existent")
        
        # Force initial retrieval to be empty so balancing kicks in specifically
        with patch('pathlib.Path.exists', return_value=False):
            with patch('src.engine.rag.retriever.keyword_search') as mock_kw:
                # First call (Fallback) returns nothing
                # Second call (Balancing) should happen
                
                # We need keyword_search to behave logically:
                # 1. Fallback search -> []
                # 2. Balancing search for 'service' -> should prioritize 'user' if query is 'user'
                
                def kw_side_effect(query, symbols, top_k, language_profile):
                    if len(symbols) == 3: return [] # Fallback
                    if len(symbols) == 2: return [self.s1] # Balancing (UserService vs StringUtils)
                    return []
                
                mock_kw.side_effect = kw_side_effect
                
                # We need to spy on _balance_layers actually
                # But let's just run retrieve
                results = retriever.retrieve_relevant_symbols("user logic", self.all_symbols)
                
                # Check if we got the balanced symbol
                self.assertTrue(any(s.name == "UserService" for s in results))

if __name__ == '__main__':
    unittest.main()
