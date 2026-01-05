"""Language Profile Loader - Load language-specific QA/Design rules from YAML"""
from pathlib import Path
from typing import Optional
import yaml

from src.utils.logger import get_logger

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


def load_language_profile(
    language_name: Optional[str] = None,
    profile_dir: Optional[str] = None,
    config = None
) -> LanguageProfile:
    """
    Load language profile from YAML file
    
    Args:
        language_name: Language name (e.g., 'java', 'python'). 
                      If None, reads from config.language.name (default: 'java')
        profile_dir: Directory containing profile YAML files.
                    If None, reads from config.language.profile_dir or defaults to 'configs/language'
        config: Config instance. If None, creates new Config()
    
    Returns:
        LanguageProfile: Loaded and validated language profile
    
    Raises:
        FileNotFoundError: If profile file doesn't exist
        ValueError: If profile validation fails
    """
    # Import here to avoid circular dependency
    if config is None:
        from src.utils.config import Config
        config = Config()
    
    # Determine language name
    if language_name is None:
        language_name = config.get("language.name", "java")
        logger.info(f"Using language from config: {language_name}")
    
    # Determine profile directory
    if profile_dir is None:
        profile_dir = config.get("language.profile_dir", "configs/language")
    
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
