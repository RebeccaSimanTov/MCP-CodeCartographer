"""
LLM Configuration - Complete multi-provider support
מימוש מלא של תמיכה בכל ספקי ה-LLM
"""
import os
from typing import Literal, Dict, Any
from dotenv import load_dotenv
print("="*80)
print("🔑 CHECKING API KEYS")
print("="*80)
print(f"OPENAI_API_KEY exists: {bool(os.getenv('OPENAI_API_KEY'))}")
print(f"OPENAI_API_KEY value: {os.getenv('OPENAI_API_KEY')[:20]}..." if os.getenv('OPENAI_API_KEY') else "NOT SET")
print("="*80)

# Load environment variables
external_env_path = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), 
    ".env"
)
load_dotenv(external_env_path)
print("OPENAI_API_KEY =", os.getenv("OPENAI_API_KEY"))
LLMProvider = Literal["gemini", "openai", "anthropic"]


class LLMConfig:
    """
    מרכז תצורה לכל ספקי ה-LLM
    כאן מגדירים הכל במקום אחד!
    """
    
    # ⚙️ Default provider - שנה כאן לשנות את ברירת המחדל
    DEFAULT_PROVIDER: LLMProvider = "openai"
    
    # 🎛️ Model configurations - כל ההגדרות למודלים
    MODELS: Dict[str, Dict[str, Any]] = {
        "gemini": {
            "model": "gemini-2.0-flash-exp",
            "temperature": 0.0,
            "api_key_env": "GEMINI_API_KEY",
            "supports_structured_output": True,
            "max_tokens": 8192,
            "timeout": 60,
        },
        "openai": {
            "model": "gpt-4o",
            "temperature": 0.0,
            "api_key_env": "OPENAI_API_KEY",
            "supports_structured_output": True,
            "max_tokens": 4096,
            "timeout": 60,
        },
        "anthropic": {
            "model": "claude-3-5-sonnet-20241022",
            "temperature": 0.0,
            "api_key_env": "ANTHROPIC_API_KEY",
            "supports_structured_output": True,
            "max_tokens": 4096,
            "timeout": 60,
        }
    }
    
    # 🔧 Agent configuration
    AGENT_CONFIG = {
        "max_iterations": 30,
        "max_execution_time": 2000,  
        "verbose": True,
        "handle_parsing_errors": True,
        "return_intermediate_steps": True,
    }
    
    # 💾 Memory configuration
    MEMORY_CONFIG = {
        "max_token_limit": 200000,  # Max tokens to keep in memory
        "return_messages": True,
    }
    
    @classmethod
    def get_api_key(cls, provider: LLMProvider) -> str:
        """קבל API key לספק"""
        config = cls.MODELS.get(provider)
        if not config:
            raise ValueError(f"Unknown provider: {provider}")
        
        api_key = os.getenv(config["api_key_env"])
        if not api_key:
            raise ValueError(
                f"❌ Missing API key for {provider}!\n"
                f"Please set {config['api_key_env']} in your .env file"
            )
        
        return api_key
    
    @classmethod
    def get_model_config(cls, provider: LLMProvider) -> Dict[str, Any]:
        """קבל את כל התצורה למודל"""
        config = cls.MODELS.get(provider)
        if not config:
            raise ValueError(f"Unknown provider: {provider}")
        return config.copy()
    
    @classmethod
    def get_model_name(cls, provider: LLMProvider) -> str:
        """קבל שם המודל"""
        return cls.get_model_config(provider)["model"]
    
    @classmethod
    def get_temperature(cls, provider: LLMProvider) -> float:
        """קבל temperature"""
        return cls.get_model_config(provider)["temperature"]
    
    @classmethod
    def supports_structured_output(cls, provider: LLMProvider) -> bool:
        """בדוק אם תומך ב-structured output"""
        return cls.get_model_config(provider).get("supports_structured_output", False)
    
    @classmethod
    def list_available_providers(cls) -> list[str]:
        """רשימת כל הספקים הזמינים"""
        available = []
        for provider in cls.MODELS.keys():
            try:
                cls.get_api_key(provider)
                available.append(provider)
            except ValueError:
                pass
        return available
    
    @classmethod
    def validate_provider(cls, provider: LLMProvider) -> bool:
        """ודא שהספק תקין וה-API key קיים"""
        try:
            cls.get_api_key(provider)
            return True
        except ValueError:
            return False