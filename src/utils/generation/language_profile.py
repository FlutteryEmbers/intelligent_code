"""Language Profile Loader - Load language-specific QA/Design rules from YAML"""
from pathlib import Path
from typing import Optional
import yaml

from src.utils.core.logger import get_logger

logger = get_logger(__name__)

# Module-level cache to avoid repeated file reads
_profile_cache = {}


class LanguageProfile:
    """Language profile containing QA and Design generation rules"""
    
    def __init__(self, data: dict):
        """Initialize from YAML data dict"""
        self._validate_schema(data)
        self.data = data
        self.language = data["language"]
    
    @staticmethod
    def _validate_schema(data: dict):
        """Validate that profile has required fields"""
        required_fields = ["language", "parsing", "qa", "design"]
        missing = [f for f in required_fields if f not in data]
        if missing:
            raise ValueError(f"Language profile missing required fields: {missing}")
        
        # Validate system_prompts (optional but recommended)
        if "system_prompts" in data:
            prompts = data["system_prompts"]
            if not isinstance(prompts, dict):
                raise ValueError("system_prompts must be a dict")
            # Check for default and reasoning prompts (recommended)
            if "default" not in prompts:
                logger.warning("system_prompts missing 'default' prompt (recommended)")
            if "reasoning" not in prompts:
                logger.warning("system_prompts missing 'reasoning' prompt (recommended)")
        
        # Validate Parsing structure
        parsing = data.get("parsing", {})
        required_parsing_fields = ["file_extensions", "ignore_paths", "max_chars_per_symbol"]
        missing_parsing = [f for f in required_parsing_fields if f not in parsing]
        if missing_parsing:
            raise ValueError(f"Parsing config missing fields: {missing_parsing}")
        
        # Validate QA structure
        qa = data.get("qa", {})
        if "markers" not in qa:
            raise ValueError("Language profile missing 'qa.markers'")
        if "scoring" not in qa:
            raise ValueError("Language profile missing 'qa.scoring'")
        
        markers = qa["markers"]
        required_marker_fields = ["annotations", "decorators", "name_keywords", "path_keywords"]
        missing_markers = [f for f in required_marker_fields if f not in markers]
        if missing_markers:
            raise ValueError(f"QA markers missing fields: {missing_markers}")
        
        # Validate Design structure
        design = data.get("design", {})
        if "layers" not in design:
            raise ValueError("Language profile missing 'design.layers'")
        
        layers = design["layers"]
        required_layers = ["controller", "service", "repository"]
        missing_layers = [l for l in required_layers if l not in layers]
        if missing_layers:
            raise ValueError(f"Design layers missing: {missing_layers}")
        
        # Validate each layer has required fields
        for layer_name, layer_data in layers.items():
            required_layer_fields = ["annotations", "decorators", "name_keywords", "path_keywords"]
            missing_layer_fields = [f for f in required_layer_fields if f not in layer_data]
            if missing_layer_fields:
                raise ValueError(f"Layer '{layer_name}' missing fields: {missing_layer_fields}")
    
    def get_qa_markers(self) -> dict:
        """Get QA generation markers"""
        return self.data["qa"]["markers"]
    
    def get_qa_scoring(self) -> dict:
        """Get QA scoring weights"""
        return self.data["qa"]["scoring"]
    
    def get_design_layer(self, layer_name: str) -> dict:
        """Get design layer rules (controller/service/repository)"""
        return self.data["design"]["layers"].get(layer_name, {})
    
    def get_all_design_layers(self) -> dict:
        """Get all design layer rules"""
        return self.data["design"]["layers"]
    
    def get_parsing_config(self) -> dict:
        """Get parsing configuration (file extensions, ignore patterns, etc.)"""
        return self.data["parsing"]
    
    def get_file_extensions(self) -> list:
        """Get file extensions to parse"""
        return self.data["parsing"]["file_extensions"]
    
    def get_ignore_paths(self) -> list:
        """Get paths to ignore during parsing"""
        return self.data["parsing"]["ignore_paths"]
    
    def get_max_chars_per_symbol(self) -> int:
        """Get max characters per symbol"""
        return self.data["parsing"]["max_chars_per_symbol"]
    
    def get_system_prompt(self, prompt_type: str = "default") -> str:
        """Get system prompt for training data export
        
        Args:
            prompt_type: Type of prompt ('default' or 'reasoning')
            
        Returns:
            System prompt string
        """
        system_prompts = self.data.get("system_prompts", {})
        return system_prompts.get(prompt_type, "")
    
    def get(self, key: str, default=None):
        """Get value from profile data with optional default"""
        return self.data.get(key, default)
    
    def __getitem__(self, key: str):
        """Support dict-style access"""
        return self.data[key]
    
    def __contains__(self, key: str) -> bool:
        """Support 'in' operator"""
        return key in self.data
    
    # Layer identification methods
    def is_controller(self, symbol) -> bool:
        """Check if symbol is a controller using profile rules
        
        Args:
            symbol: CodeSymbol object with annotations, name, qualified_name, file_path
            
        Returns:
            bool: True if symbol matches controller layer rules
        """
        layer_rules = self.get_design_layer('controller')
        return self._matches_layer_rules(symbol, layer_rules)
    
    def is_service(self, symbol) -> bool:
        """Check if symbol is a service using profile rules
        
        Args:
            symbol: CodeSymbol object
            
        Returns:
            bool: True if symbol matches service layer rules
        """
        layer_rules = self.get_design_layer('service')
        return self._matches_layer_rules(symbol, layer_rules)
    
    def is_repository(self, symbol) -> bool:
        """Check if symbol is a repository using profile rules
        
        Args:
            symbol: CodeSymbol object
            
        Returns:
            bool: True if symbol matches repository layer rules
        """
        layer_rules = self.get_design_layer('repository')
        return self._matches_layer_rules(symbol, layer_rules)
    
    def get_layer(self, symbol) -> str | None:
        """Get the layer type for a symbol
        
        Args:
            symbol: CodeSymbol object
            
        Returns:
            str | None: 'controller', 'service', 'repository', or None
        """
        if self.is_controller(symbol):
            return 'controller'
        if self.is_service(symbol):
            return 'service'
        if self.is_repository(symbol):
            return 'repository'
        return None
    
    def filter_by_layer(self, symbols: list, layer: str) -> list:
        """Filter symbols by layer type
        
        Args:
            symbols: List of CodeSymbol objects
            layer: Layer type ('controller', 'service', 'repository')
            
        Returns:
            list: Symbols matching the specified layer
        """
        layer_check = {
            'controller': self.is_controller,
            'service': self.is_service,
            'repository': self.is_repository,
        }.get(layer)
        
        if not layer_check:
            return []
        return [s for s in symbols if layer_check(s)]
    
    def _matches_layer_rules(self, symbol, layer_rules: dict) -> bool:
        """Generic layer matching based on profile rules
        
        Args:
            symbol: CodeSymbol object
            layer_rules: Dict with annotations, decorators, name_keywords, path_keywords
            
        Returns:
            bool: True if symbol matches any rule
        """
        # Check annotations/decorators (both in symbol.annotations)
        symbol_annotations = {ann.name for ann in symbol.annotations}
        profile_annotations = set(layer_rules.get('annotations', []))
        profile_decorators = set(layer_rules.get('decorators', []))
        
        if symbol_annotations & (profile_annotations | profile_decorators):
            return True
        
        # Check name keywords
        name_keywords = layer_rules.get('name_keywords', [])
        name_lower = symbol.name.lower()
        qualified_lower = symbol.qualified_name.lower()
        if any(kw in name_lower or kw in qualified_lower for kw in name_keywords):
            return True
        
        # Check path keywords
        path_keywords = layer_rules.get('path_keywords', [])
        path_lower = symbol.file_path.lower()
        if any(kw in path_lower for kw in path_keywords):
            return True
        
        return False


def load_language_profile(
    config = None,
    language_name: Optional[str] = None,
    profile_dir: Optional[str] = None
) -> LanguageProfile:
    """
    Load language profile from YAML file
    
    Args:
        config: Config instance or dict. If None, creates new Config()
        language_name: Language name (e.g., 'java', 'python'). 
                      If None, reads from config.language.name (default: 'java')
        profile_dir: Directory containing profile YAML files.
                    If None, reads from config.language.profile_dir or defaults to 'configs/language'
    
    Returns:
        LanguageProfile: Loaded and validated language profile
    
    Raises:
        FileNotFoundError: If profile file doesn't exist
        ValueError: If profile validation fails
    """
    # Import here to avoid circular dependency
    if config is None:
        from src.utils.core.config import Config
        config = Config()
    
    # Check if config is Config object or dict
    from src.utils.core.config import Config as ConfigClass
    
    # Determine language name
    if language_name is None:
        if isinstance(config, ConfigClass):
            # Config object - access internal _config dict
            language_name = config._config.get("language", {}).get("name", "java")
        else:
            # Regular dict
            language_name = config.get("language", {}).get("name", "java")
        logger.info(f"Using language from config: {language_name}")
    
    # Determine profile directory
    if profile_dir is None:
        if isinstance(config, ConfigClass):
            profile_dir = config._config.get("language", {}).get("profile_dir", "configs/language")
        else:
            profile_dir = config.get("language", {}).get("profile_dir", "configs/language")
    
    # Check cache
    cache_key = f"{profile_dir}/{language_name}"
    if cache_key in _profile_cache:
        logger.debug(f"Using cached language profile: {cache_key}")
        return _profile_cache[cache_key]
    
    # Construct profile path
    profile_path = Path(profile_dir) / f"{language_name}.yaml"
    
    if not profile_path.exists():
        raise FileNotFoundError(
            f"Language profile not found: {profile_path}\n"
            f"Please create a profile YAML file for language '{language_name}'"
        )
    
    # Load YAML
    try:
        with open(profile_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
        
        if not data:
            raise ValueError(f"Empty profile file: {profile_path}")
        
        # Create and validate profile
        profile = LanguageProfile(data)
        
        # Cache it
        _profile_cache[cache_key] = profile
        
        logger.info(f"Loaded language profile: {language_name} from {profile_path}")
        return profile
        
    except yaml.YAMLError as e:
        raise ValueError(f"Failed to parse YAML profile {profile_path}: {e}")
    except Exception as e:
        raise ValueError(f"Failed to load language profile {profile_path}: {e}")


def clear_profile_cache():
    """Clear the profile cache (useful for testing)"""
    global _profile_cache
    _profile_cache = {}
