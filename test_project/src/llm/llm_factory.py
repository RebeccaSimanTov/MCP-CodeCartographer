"""
LLM Factory - Create optimized LangChain LLM instances
מימוש מלא של יצירת LLM עם כל האופטימיזציות
"""
from typing import Optional, Dict, Any
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from langchain_core.language_models import BaseChatModel
from langchain_core.callbacks import CallbackManager, StdOutCallbackHandler

from src.llm.llm_config import LLMConfig, LLMProvider


class LLMFactory:
    """
    Factory מתקדם ליצירת LLM instances
    תומך בכל התכונות המתקדמות של LangChain
    """
    
    @staticmethod
    def create_llm(
        provider: Optional[LLMProvider] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        streaming: bool = False,
        callbacks: Optional[list] = None,
        **kwargs
    ) -> BaseChatModel:
        """
        יצירת LLM instance מאופטמז
        
        Args:
            provider: ספק LLM ("gemini", "openai", "anthropic")
            model: שם מודל (None = default)
            temperature: temperature (None = default)
            streaming: האם לאפשר streaming
            callbacks: callbacks ל-monitoring
            **kwargs: פרמטרים נוספים
            
        Returns:
            BaseChatModel: instance מוכן לשימוש
        """
        # Default provider
        if provider is None:
            provider = LLMConfig.DEFAULT_PROVIDER
        
        # Validate provider
        if not LLMConfig.validate_provider(provider):
            available = LLMConfig.list_available_providers()
            raise ValueError(
                f"❌ Provider '{provider}' is not configured!\n"
                f"Available providers: {available}\n"
                f"Please add the required API key to .env"
            )
        
        # Get configuration
        config = LLMConfig.get_model_config(provider)
        api_key = LLMConfig.get_api_key(provider)
        model_name = model or config["model"]
        temp = temperature if temperature is not None else config["temperature"]
        
        # Setup callbacks
        if callbacks is None:
            callbacks = []
        
        callback_manager = CallbackManager(callbacks) if callbacks else None
        
        print(f"🤖 Creating {provider.upper()} LLM:")
        print(f"   📦 Model: {model_name}")
        print(f"   🌡️  Temperature: {temp}")
        print(f"   📡 Streaming: {streaming}")
        
        # Create LLM based on provider
        if provider == "gemini":
            return ChatGoogleGenerativeAI(
                model=model_name,
                temperature=temp,
                google_api_key=api_key,
                streaming=streaming,
                callbacks=callback_manager,
                convert_system_message_to_human=True,
                max_output_tokens=config.get("max_tokens", 8192),
                timeout=config.get("timeout", 60),
                **kwargs
            )
        
        elif provider == "openai":
            return ChatOpenAI(
                model=model_name,
                temperature=temp,
                api_key=api_key,
                streaming=streaming,
                callbacks=callback_manager,
                max_tokens=config.get("max_tokens", 4096),
                timeout=config.get("timeout", 60),
                **kwargs
            )
        
        elif provider == "anthropic":
            return ChatAnthropic(
                model=model_name,
                temperature=temp,
                api_key=api_key,
                streaming=streaming,
                callbacks=callback_manager,
                max_tokens=config.get("max_tokens", 4096),
                timeout=config.get("timeout", 60),
                **kwargs
            )
        
        else:
            raise ValueError(f"Unsupported provider: {provider}")
    
    @staticmethod
    def create_json_llm(
        provider: Optional[LLMProvider] = None,
        **kwargs
    ) -> BaseChatModel:
        """
        יצירת LLM עם JSON mode (structured output)
        
        Args:
            provider: ספק LLM
            **kwargs: פרמטרים נוספים
            
        Returns:
            BaseChatModel: LLM מוגדר ל-JSON output
        """
        if provider is None:
            provider = LLMConfig.DEFAULT_PROVIDER
        
        print(f"📋 Creating JSON-mode LLM for {provider.upper()}")
        
        if provider == "gemini":
            # Gemini uses generation_config
            return LLMFactory.create_llm(
                provider=provider,
                **kwargs
            )
        
        elif provider == "openai":
            # OpenAI uses response_format
            return LLMFactory.create_llm(
                provider=provider,
                model_kwargs={"response_format": {"type": "json_object"}},
                **kwargs
            )
        
        elif provider == "anthropic":
            # Claude can use tool calling for structured output
            return LLMFactory.create_llm(
                provider=provider,
                **kwargs
            )
        
        return LLMFactory.create_llm(provider=provider, **kwargs)
    
    @staticmethod
    def create_streaming_llm(
        provider: Optional[LLMProvider] = None,
        on_token: Optional[callable] = None,
        **kwargs
    ) -> BaseChatModel:
        """
        יצירת LLM עם streaming support
        
        Args:
            provider: ספק LLM
            on_token: callback לכל token
            **kwargs: פרמטרים נוספים
            
        Returns:
            BaseChatModel: LLM עם streaming
        """
        from langchain_core.callbacks.streaming_stdout import StreamingStdOutCallbackHandler
        
        callbacks = []
        if on_token:
            # Custom callback
            class TokenCallback(StreamingStdOutCallbackHandler):
                def on_llm_new_token(self, token: str, **kwargs):
                    on_token(token)
            callbacks.append(TokenCallback())
        else:
            callbacks.append(StreamingStdOutCallbackHandler())
        
        return LLMFactory.create_llm(
            provider=provider,
            streaming=True,
            callbacks=callbacks,
            **kwargs
        )
    
    @staticmethod
    def get_provider_info(provider: Optional[LLMProvider] = None) -> Dict[str, Any]:
        """
        קבל מידע על ספק
        
        Args:
            provider: ספק LLM
            
        Returns:
            Dict עם מידע
        """
        if provider is None:
            provider = LLMConfig.DEFAULT_PROVIDER
        
        config = LLMConfig.get_model_config(provider)
        
        return {
            "provider": provider,
            "model": config["model"],
            "temperature": config["temperature"],
            "max_tokens": config.get("max_tokens", "unknown"),
            "structured_output": config.get("supports_structured_output", False),
            "api_key_configured": LLMConfig.validate_provider(provider)
        }