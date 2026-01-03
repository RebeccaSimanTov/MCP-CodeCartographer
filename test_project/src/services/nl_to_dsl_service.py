"""
NL to DSL Service - Converts natural language to structured DSL
FIXED: Uses LLMFactory instead of missing LLMService
"""
import os
import json
from typing import Dict, Any
from pathlib import Path

# Import domain models
from common.models.orchestrator.openai_models import OpenAIResponse
from common.models.orchestrator.workflow_models import DSLModel
from common.utils.json_utils import dumps_safe
from common.utils.redis_client import get_nl2dsl_translation, set_nl2dsl_translation
from common.utils.semantic_cache import (
    get_semantic_test_details,
    set_semantic_test_details
)
# ✅ FIXED: Import LLMFactory instead of LLMService
from src.llm.llm_factory import LLMFactory


class NL2DSLService:
    """
    Service for converting natural language to DSL
    FIXED: Direct LLM usage without external service dependency
    """
    
    async def _load_workflow_schema(self) -> Dict[str, Any]:
        """Load workflow schema from /app/common/dsl_schemas/orchestrator/workflow.schema.json"""
        try:
            # Simple absolute path - no complexity
            schema_path = "/app/common/dsl_schemas/orchestrator/workflow.schema.json"
            
            async def read_file_async(path):
                import aiofiles
                async with aiofiles.open(path, 'r', encoding='utf-8') as f:
                    return await f.read()
            
            schema_content = await read_file_async(schema_path)
            
            if not schema_content:
                raise ValueError("workflow.schema.json is empty")
                
            return json.loads(schema_content)
            
        except (FileNotFoundError, json.JSONDecodeError, ValueError) as e:
            raise RuntimeError(f"Could not load workflow.schema.json: {e}")
    
    def __init__(self, ctx=None):
        repo_root = Path(__file__).resolve().parents[2]
        self.ctx = ctx
        
        # ✅ FIXED: Create LLM directly using LLMFactory
        self.llm = None  # Will be created on first use
        
        self._schema_coro = self._load_workflow_schema()
        self.schema = None
        self.llm_instructions_file = ""
        
        # Load instructions
        instructions_path = repo_root / "prompts" / "nl2dsl_instructions.md"
        try:
            with open(instructions_path, 'r', encoding='utf-8') as f:
                self.llm_instructions_file = f.read().strip()

            if not self.llm_instructions_file:
                raise ValueError("instructions.md is empty")
        except Exception as e:
            print(f"   ❌ Failed to load instructions from {instructions_path}: {e}")
            self.llm_instructions_file = (
                "You are an orchestration LLM that decides the next tool to call "
                "based on the current state. Use the available MCP tools to fulfill "
                "the user's query step-by-step."
            )

    async def ensure_schema_loaded(self):
        """Ensure schema is loaded"""
        if self.schema is None:
            self.schema = await self._schema_coro

    def _get_or_create_llm(self):
        """Get or create LLM instance"""
        if self.llm is None:
            # Create Gemini LLM for JSON output
            self.llm = LLMFactory.create_llm(
                provider="openai",
                temperature=0.0
            )
        return self.llm

    async def parse_natural_language(self, input_text: str) -> DSLModel:
        """
        Converts natural-language text into DSLModel using LLM
        FIXED: Direct LLM invocation
        """
        await self.ensure_schema_loaded()

        # Check cache
        cached_dsl = await get_nl2dsl_translation(input_text)
        if cached_dsl:
            print("⚡ NL2DSL cache hit!")
            return DSLModel.model_validate({"input": input_text, "output": cached_dsl})

        try:
            if self.ctx:
                await self.ctx.info(f"parse_natural_language called with input: {input_text}")
            
            # Build system prompt
            system_prompt = self.llm_instructions_file
            system_message = f"{system_prompt}\n\nJSON Schema: {dumps_safe(self.schema)}"
            
            # ✅ FIXED: Direct LLM invocation using LangChain
            from langchain_core.messages import SystemMessage, HumanMessage
            
            llm = self._get_or_create_llm()
            
            messages = [
                SystemMessage(content=system_message),
                HumanMessage(content=f"User request:\n{input_text}")
            ]
            
            # Invoke LLM
            response = await llm.ainvoke(messages)
            
            if self.ctx:
                await self.ctx.debug(f"parse_natural_language response: {response}")
            
            # Extract JSON from response
            dsl_dict = self._extract_json_from_response(response.content)
            
            # Wrap in proper format
            result_dict = {
                "input": input_text,
                "output": dsl_dict
            }

            test_details = dsl_dict.get("test_details", {})
            if test_details and "description" in test_details:
                similar = await get_semantic_test_details(test_details["description"])
                if similar:
                    print("⚡ Semantic test_details cache hit!")
                    dsl_dict["test_details"]["name"] = similar.get(
                        "name", dsl_dict["test_details"].get("name", "")
                    )
                    dsl_dict["test_details"]["description"] = similar.get(
                        "description", dsl_dict["test_details"].get("description", "")
                    )
                else:
                    await set_semantic_test_details(test_details)
            
            # Cache result
            await set_nl2dsl_translation(input_text, dsl_dict)
            
            # Return as DSLModel
            return DSLModel.model_validate(result_dict)

        except Exception as e:
            if self.ctx:
                await self.ctx.error(f"parse_natural_language failed: {e}")
            
            # Return default fallback
            return DSLModel.model_validate({
                "input": input_text, 
                "output": {
                    "action": "unknown",
                    "target": "",
                    "parameters": {"filters": [], "values": []},
                    "conditions": []
                }
            })
    
    def _extract_json_from_response(self, content: str) -> Dict[str, Any]:
        """
        Extract JSON from LLM response
        FIXED: Handle string content from LangChain
        """
        try:
            # If content is already a dict
            if isinstance(content, dict):
                if "input" in content or "output" in content:
                    return content.get("output", content)
                return content
            
            # If content is a string
            if isinstance(content, str):
                text = content.strip()
                
                # Remove markdown code fences
                if text.startswith("```"):
                    text = text.strip("`")
                    if "\n" in text:
                        # Remove language identifier
                        text = "\n".join(text.split("\n")[1:])
                
                # Try to parse as JSON
                parsed = json.loads(text)
                
                # If it has 'output' key, return that
                if isinstance(parsed, dict) and "output" in parsed:
                    return parsed["output"]
                
                return parsed
            
            # Fallback
            raise ValueError("Could not extract JSON from response")

        except Exception as e:
            print(f"⚠️  Error extracting JSON: {e}")
            # Return default fallback
            return {
                "action": "unknown",
                "target": "",
                "parameters": {"filters": [], "values": []},
                "conditions": []
            }