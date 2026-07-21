import logging
import json
from typing import List, Dict, Any, Optional
from core.config import settings

logger = logging.getLogger(__name__)

class LLMClient:
    """
    Unified LLM Client wrapper supporting OpenAI, Gemini, Anthropic, and Groq APIs.
    Communicates via raw HTTP requests using 'requests' (with a fallback to 'urllib.request').
    """

    def __init__(self):
        try:
            import requests
            self.requests = requests
        except ImportError:
            self.requests = None
            logger.warning("requests library not found. Falling back to urllib.request.")

    def detect_provider(self) -> Optional[str]:
        """
        Determines the active provider based on configured API keys.
        Priority: OpenAI -> Gemini -> Anthropic -> Groq
        """
        if settings.OPENAI_API_KEY:
            return "openai"
        if settings.GEMINI_API_KEY:
            return "gemini"
        if settings.ANTHROPIC_API_KEY:
            return "anthropic"
        if settings.GROQ_API_KEY:
            return "groq"
        return None

    def complete(self, messages: List[Dict[str, str]], provider: Optional[str] = None, **kwargs) -> Optional[str]:
        """
        Submits chat messages to the target or auto-detected provider.
        """
        if not provider:
            provider = self.detect_provider()
            if not provider:
                logger.warning("No LLM API keys configured. Cannot complete chat.")
                return None

        provider = provider.lower()
        if provider == "openai":
            return self._call_openai(messages, **kwargs)
        elif provider == "gemini":
            return self._call_gemini(messages, **kwargs)
        elif provider == "anthropic":
            return self._call_anthropic(messages, **kwargs)
        elif provider == "groq":
            return self._call_groq(messages, **kwargs)
        else:
            logger.error(f"Unsupported provider: {provider}")
            return None

    def _send_request(self, url: str, headers: Dict[str, str], payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Sends HTTP POST request using either requests or urllib.request."""
        if self.requests:
            try:
                response = self.requests.post(url, headers=headers, json=payload, timeout=30)
                response.raise_for_status()
                return response.json()
            except Exception as e:
                logger.error(f"HTTP request failed using requests: {e}")
                if self.requests and hasattr(e, 'response') and e.response is not None:
                    logger.error(f"Response body: {e.response.text}")
                return None
        else:
            import urllib.request
            import urllib.error
            data_bytes = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(url, data=data_bytes, headers=headers, method="POST")
            try:
                with urllib.request.urlopen(req, timeout=30) as response:
                    res_bytes = response.read()
                    return json.loads(res_bytes.decode("utf-8"))
            except urllib.error.HTTPError as e:
                err_body = e.read().decode("utf-8") if e else ""
                logger.error(f"HTTPError in urllib: {e.code} - {e.reason}. Body: {err_body}")
                return None
            except Exception as e:
                logger.error(f"Exception in urllib: {e}")
                return None

    def _call_openai(self, messages: List[Dict[str, str]], **kwargs) -> Optional[str]:
        url = f"{settings.OPENAI_API_BASE.rstrip('/')}/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {settings.OPENAI_API_KEY}"
        }
        payload = {
            "model": settings.OPENAI_MODEL,
            "messages": messages,
            "temperature": kwargs.get("temperature", 0.7),
            "max_tokens": kwargs.get("max_tokens", 800)
        }
        res = self._send_request(url, headers, payload)
        if res and "choices" in res:
            try:
                return res["choices"][0]["message"]["content"]
            except (KeyError, IndexError) as e:
                logger.error(f"Failed parsing OpenAI response choices: {e}")
        return None

    def _call_groq(self, messages: List[Dict[str, str]], **kwargs) -> Optional[str]:
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {settings.GROQ_API_KEY}"
        }
        payload = {
            "model": settings.GROQ_MODEL,
            "messages": messages,
            "temperature": kwargs.get("temperature", 0.7),
            "max_tokens": kwargs.get("max_tokens", 800)
        }
        res = self._send_request(url, headers, payload)
        if res and "choices" in res:
            try:
                return res["choices"][0]["message"]["content"]
            except (KeyError, IndexError) as e:
                logger.error(f"Failed parsing Groq response choices: {e}")
        return None

    def _call_anthropic(self, messages: List[Dict[str, str]], **kwargs) -> Optional[str]:
        url = "https://api.anthropic.com/v1/messages"
        headers = {
            "x-api-key": settings.ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        }
        system_content = None
        filtered_messages = []
        for msg in messages:
            if msg["role"] == "system":
                system_content = msg["content"]
            else:
                filtered_messages.append(msg)

        payload = {
            "model": settings.ANTHROPIC_MODEL,
            "messages": filtered_messages,
            "max_tokens": kwargs.get("max_tokens", 1024),
            "temperature": kwargs.get("temperature", 0.7)
        }
        if system_content:
            payload["system"] = system_content

        res = self._send_request(url, headers, payload)
        if res and "content" in res:
            try:
                return res["content"][0]["text"]
            except (KeyError, IndexError) as e:
                logger.error(f"Failed parsing Anthropic response content: {e}")
        return None

    def _call_gemini(self, messages: List[Dict[str, str]], **kwargs) -> Optional[str]:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{settings.GEMINI_MODEL}:generateContent?key={settings.GEMINI_API_KEY}"
        headers = {
            "Content-Type": "application/json"
        }
        contents = []
        system_instruction = None
        for msg in messages:
            role = msg["role"]
            content = msg["content"]
            if role == "system":
                system_instruction = {"parts": [{"text": content}]}
            else:
                contents.append({
                    "role": "user" if role == "user" else "model",
                    "parts": [{"text": content}]
                })

        payload = {
            "contents": contents,
            "generationConfig": {
                "temperature": kwargs.get("temperature", 0.7),
                "maxOutputTokens": kwargs.get("max_tokens", 800)
            }
        }
        if system_instruction:
            payload["systemInstruction"] = system_instruction

        res = self._send_request(url, headers, payload)
        if res and "candidates" in res:
            try:
                return res["candidates"][0]["content"]["parts"][0]["text"]
            except (KeyError, IndexError) as e:
                logger.error(f"Failed parsing Gemini response parts: {e}")
        return None
