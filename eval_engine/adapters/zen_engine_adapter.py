"""
Zen Engine Adapter for django-eval

Provides seamless integration with Zen Engine (https://github.com/gorules/zen)
while maintaining compatibility with existing SimpleEval and Decision Table engines.
"""

from typing import Any, Dict, Optional, List
import json
import logging
from dataclasses import dataclass
from enum import Enum

from django.core.serializers.json import DjangoJSONEncoder
from django.conf import settings

logger = logging.getLogger(__name__)


class EngineType(str, Enum):
    """Supported rule engine types"""
    SIMPLE_EVAL = "simple_eval"
    DECISION_TABLE = "decision_table"
    ZEN_ENGINE = "zen_engine"


@dataclass
class ZenEngineConfig:
    """Configuration for Zen Engine connection"""
    endpoint: str = "localhost:50051"
    timeout: float = 5.0
    max_retries: int = 3
    use_ssl: bool = False
    api_key: Optional[str] = None


class ZenEngineAdapter:
    """
    Adapter for Zen Engine integration.
    
    Supports both gRPC and HTTP communication modes.
    Handles context serialization, error handling, and connection pooling.
    """
    
    def __init__(self, config: Optional[ZenEngineConfig] = None):
        self.config = config or ZenEngineConfig()
        self._channel = None
        self._stub = None
        
    def _get_channel(self):
        """Get or create gRPC channel (singleton pattern)"""
        if self._channel is None:
            try:
                import grpc
                if self.config.use_ssl:
                    credentials = grpc.ssl_channel_credentials()
                    self._channel = grpc.secure_channel(
                        self.config.endpoint, 
                        credentials
                    )
                else:
                    self._channel = grpc.insecure_channel(self.config.endpoint)
                    
                # Import Zen Engine stub
                from zen_engine_pb2_grpc import ZenEngineStub
                self._stub = ZenEngineStub(self._channel)
                
            except ImportError:
                logger.warning("grpcio not installed, falling back to HTTP mode")
                self._channel = "http"
            except Exception as e:
                logger.error(f"Failed to create gRPC channel: {e}")
                self._channel = "http"
                
        return self._channel
    
    def _serialize_context(self, context: Dict[str, Any]) -> str:
        """
        Safely serialize context data, handling Django-specific types.
        
        Args:
            context: Input context dictionary
            
        Returns:
            JSON string representation
        """
        try:
            return json.dumps(context, cls=DjangoJSONEncoder)
        except Exception as e:
            logger.error(f"Context serialization failed: {e}")
            # Fallback: convert problematic types manually
            safe_context = self._make_context_safe(context)
            return json.dumps(safe_context, cls=DjangoJSONEncoder)
    
    def _make_context_safe(self, obj: Any) -> Any:
        """Recursively convert non-serializable objects to safe types"""
        if isinstance(obj, dict):
            return {k: self._make_context_safe(v) for k, v in obj.items()}
        elif isinstance(obj, (list, tuple)):
            return [self._make_context_safe(item) for item in obj]
        elif hasattr(obj, 'isoformat'):  # datetime, date
            return obj.isoformat()
        elif hasattr(obj, '__float__'):  # Decimal
            try:
                return float(obj)
            except:
                return str(obj)
        elif hasattr(obj, 'hex'):  # UUID
            return str(obj)
        else:
            return obj
    
    def execute(
        self, 
        rule_definition: str, 
        context: Dict[str, Any],
        timeout: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Execute rule using Zen Engine.
        
        Args:
            rule_definition: Zen Engine rule definition (JSON/YAML)
            context: Input context data
            timeout: Execution timeout in seconds
            
        Returns:
            Rule execution result
        """
        timeout = timeout or self.config.timeout
        
        try:
            if self._get_channel() == "http":
                return self._execute_http(rule_definition, context, timeout)
            else:
                return self._execute_grpc(rule_definition, context, timeout)
                
        except Exception as e:
            logger.error(f"Zen Engine execution failed: {e}")
            raise
    
    def _execute_grpc(
        self, 
        rule_definition: str, 
        context: Dict[str, Any],
        timeout: float
    ) -> Dict[str, Any]:
        """Execute via gRPC"""
        import grpc
        
        context_json = self._serialize_context(context)
        
        try:
            request = type('Request', (), {
                'rule': rule_definition,
                'context': context_json
            })()
            
            response = self._stub.Execute(
                request,
                timeout=timeout
            )
            
            return json.loads(response.result)
            
        except grpc.RpcError as e:
            if e.code() == grpc.StatusCode.DEADLINE_EXCEEDED:
                raise TimeoutError(f"Zen Engine execution timed out after {timeout}s")
            raise
    
    def _execute_http(
        self, 
        rule_definition: str, 
        context: Dict[str, Any],
        timeout: float
    ) -> Dict[str, Any]:
        """Execute via HTTP (fallback mode)"""
        import requests
        
        context_json = self._serialize_context(context)
        
        url = f"http://{self.config.endpoint}/api/v1/execute"
        payload = {
            "rule": rule_definition,
            "context": json.loads(context_json)
        }
        
        response = requests.post(url, json=payload, timeout=timeout)
        response.raise_for_status()
        
        return response.json()
    
    def validate(self, rule_definition: str) -> bool:
        """Validate Zen Engine rule definition"""
        try:
            if self._get_channel() == "http":
                import requests
                url = f"http://{self.config.endpoint}/api/v1/validate"
                response = requests.post(url, json={"rule": rule_definition}, timeout=5.0)
                return response.status_code == 200
            else:
                request = type('Request', (), {'rule': rule_definition})()
                response = self._stub.Validate(request, timeout=5.0)
                return response.valid
        except Exception as e:
            logger.error(f"Validation failed: {e}")
            return False
    
    def close(self):
        """Close gRPC channel"""
        if self._channel and self._channel != "http":
            try:
                self._channel.close()
            except:
                pass
            self._channel = None
            self._stub = None


class HybridRuleRegistry:
    """
    Unified registry supporting multiple rule engines.
    Automatically routes rules to appropriate engine based on type.
    """
    
    def __init__(self):
        self._zen_adapter = ZenEngineAdapter()
        self._engines = {}
        
    def register_engine(self, engine_type: EngineType, engine_instance: Any):
        """Register a rule engine instance"""
        self._engines[engine_type] = engine_instance
        
    def execute_rule(
        self, 
        rule_id: str,
        context: Dict[str, Any],
        engine_type: EngineType,
        rule_definition: str,
        enable_shadow_mode: bool = False
    ) -> Dict[str, Any]:
        """
        Execute rule with automatic engine routing.
        
        Args:
            rule_id: Unique rule identifier
            context: Input context
            engine_type: Target engine type
            rule_definition: Rule logic definition
            enable_shadow_mode: If True, run both engines and compare results
            
        Returns:
            Execution result with metadata
        """
        result = {
            "rule_id": rule_id,
            "engine_type": engine_type,
            "success": False,
            "result": None,
            "error": None,
            "execution_time_ms": 0,
            "shadow_result": None
        }
        
        import time
        start_time = time.time()
        
        try:
            if engine_type == EngineType.ZEN_ENGINE:
                result["result"] = self._zen_adapter.execute(rule_definition, context)
            elif engine_type in self._engines:
                engine = self._engines[engine_type]
                result["result"] = engine.evaluate(rule_definition, context)
            else:
                raise ValueError(f"Unknown engine type: {engine_type}")
                
            result["success"] = True
            
        except Exception as e:
            result["error"] = str(e)
            
        finally:
            result["execution_time_ms"] = (time.time() - start_time) * 1000
            
        # Shadow mode: compare with alternative engine
        if enable_shadow_mode and result["success"]:
            try:
                shadow_result = self._run_shadow_mode(
                    rule_id, context, engine_type, rule_definition
                )
                result["shadow_result"] = shadow_result
                
                # Log discrepancies
                if shadow_result.get("result") != result["result"]:
                    logger.warning(
                        f"Shadow mode discrepancy for rule {rule_id}: "
                        f"{result['result']} vs {shadow_result['result']}"
                    )
                    
            except Exception as e:
                logger.error(f"Shadow mode execution failed: {e}")
                
        return result
    
    def _run_shadow_mode(
        self,
        rule_id: str,
        context: Dict[str, Any],
        primary_engine: EngineType,
        rule_definition: str
    ) -> Dict[str, Any]:
        """Run rule on alternative engine for comparison"""
        # Determine shadow engine (opposite of primary)
        shadow_engine = (
            EngineType.SIMPLE_EVAL 
            if primary_engine == EngineType.ZEN_ENGINE 
            else EngineType.ZEN_ENGINE
        )
        
        # For now, just execute on shadow engine
        # In production, you'd need rule conversion logic here
        if shadow_engine == EngineType.ZEN_ENGINE:
            return self._zen_adapter.execute(rule_definition, context)
        else:
            # Would need SimpleEval adapter here
            return {"result": None, "note": "SimpleEval shadow not implemented"}


# Global registry instance
registry = HybridRuleRegistry()
