"""
LLM API 客户端
"""
import requests
import json
import os
from config import LLM_CONFIG


class LLMClient:
    def __init__(self):
        self.url = LLM_CONFIG["url"]
        self.api_key = LLM_CONFIG["api_key"]
        self.model = LLM_CONFIG["model"]

    def _ollama_base_url(self) -> str:
        # Ollama 默认监听 11434；支持 OpenAI 兼容 /v1/chat/completions（新版本）
        # 以及原生 /api/chat
        return (os.environ.get("OLLAMA_BASE_URL") or "http://127.0.0.1:11434").rstrip("/")

    def _ollama_model(self) -> str:
        # 用户可自行改成已拉取的模型，如 llama3.1:8b / qwen2.5:7b-instruct 等
        return (os.environ.get("OLLAMA_MODEL") or "qwen2.5:7b-instruct").strip()

    def _candidate_chat_urls(self) -> list[str]:
        """
        DeepSeek 文档示例为 /chat/completions；OpenAI 兼容常见为 /v1/chat/completions。
        这里做兼容：优先尝试 /chat/completions，其次 /v1/chat/completions（避免用户 base_url 配错）。
        """
        base = (self.url or "").rstrip("/")
        if not base:
            return []

        # 若用户把 base_url 配成 .../v1，则 /chat/completions 即可
        if base.endswith("/v1"):
            return [f"{base}/chat/completions"]

        return [
            f"{base}/chat/completions",
            f"{base}/v1/chat/completions",
        ]

    def _candidate_ollama_urls(self) -> list[str]:
        base = self._ollama_base_url().rstrip("/")
        return [
            f"{base}/api/chat",             # Ollama native（支持 format=json）
            f"{base}/v1/chat/completions",  # OpenAI compatible
        ]

    def _ollama_tags(self) -> tuple[bool, set[str], str]:
        """
        Returns: (reachable, model_names, err)
        """
        base = self._ollama_base_url().rstrip("/")
        try:
            r = requests.get(f"{base}/api/tags", timeout=2)
            if r.status_code != 200:
                return False, set(), f"HTTP {r.status_code}"
            data = r.json() or {}
            models = data.get("models") or []
            names = set()
            if isinstance(models, list):
                for m in models:
                    if isinstance(m, dict) and m.get("name"):
                        names.add(str(m["name"]))
            return True, names, ""
        except Exception as e:
            return False, set(), f"{type(e).__name__}: {e}"

    @staticmethod
    def _extract_openai_content(result: dict) -> str | None:
        try:
            return result["choices"][0]["message"]["content"]
        except Exception:
            return None

    @staticmethod
    def _extract_ollama_content(result: dict) -> str | None:
        # /api/chat 返回结构：{"message":{"role":"assistant","content":"..."}, ...}
        try:
            msg = result.get("message") or {}
            return msg.get("content")
        except Exception:
            return None
        
    def chat(self, messages: list, temperature: float = 0.8, max_tokens: int = 2000, timeout: int = 300) -> str:
        """
        调用LLM进行对话
        
        Args:
            messages: 消息列表，格式为 [{"role": "system/user/assistant", "content": "..."}]
            temperature: 温度参数，控制回复的随机性
            
        Returns:
            LLM的回复内容
        """
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
        
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": int(max_tokens)
        }
        
        try:
            print(f"[LLM] 模型: {self.model}")
            print(f"[LLM] 消息数量: {len(messages)}")

            # 1) 优先走配置的远程（如 DeepSeek）。若没 key，则跳过远程，直接尝试本地 Ollama。
            response = None
            used_backend = None

            if (self.api_key or "").strip():
                candidates = self._candidate_chat_urls()
                if not candidates:
                    return "[LLM_API_URL 未配置]"

                print(f"[LLM] 远程调用: {candidates[0]}")
                last_err = None
                for endpoint in candidates:
                    try:
                        response = requests.post(
                            endpoint,
                            headers=headers,
                            json=payload,
                            timeout=int(timeout)
                        )
                        if response.status_code == 404:
                            continue
                        used_backend = "remote"
                        break
                    except requests.exceptions.RequestException as e:
                        last_err = e
                        continue

                if response is None and last_err is not None:
                    print(f"[LLM] 远程请求异常，将尝试本地 Ollama: {last_err}")

            # 2) 兜底走本地 Ollama（免费，无需 key）
            if response is None:
                ollama_model = self._ollama_model()
                ollama_urls = self._candidate_ollama_urls()
                print(f"[LLM] 本地Ollama尝试: base={self._ollama_base_url()}, model={ollama_model}")

                reachable, available_models, tags_err = self._ollama_tags()
                if not reachable:
                    if not (self.api_key or "").strip():
                        return f"[LLM_API_KEY 未配置，且本地 Ollama 未启动（{self._ollama_base_url()}）]"
                    return f"[本地 Ollama 不可用（{self._ollama_base_url()}）：{tags_err}]"

                # 如果模型还没下载完/尚未拉取，会导致 /api/chat 返回 404 或长时间阻塞
                # tags 为空也意味着本机暂无任何模型可用
                if ollama_model not in available_models:
                    return f"[本地 Ollama 模型未就绪：{ollama_model}（请等待下载完成或执行：ollama pull {ollama_model}）]"

                # OpenAI compatible payload 基本一致，只需替换 model
                openai_payload = {**payload, "model": ollama_model}
                # Ollama native payload 不支持 max_tokens 顶层字段，温度走 options
                ollama_payload = {
                    "model": ollama_model,
                    "messages": messages,
                    "stream": False,
                    "options": {"temperature": temperature, "num_predict": int(max_tokens)},
                    # 强制 JSON 输出（避免 user_simulator 解析失败）
                    "format": "json",
                }

                last_err = None
                for endpoint in ollama_urls:
                    try:
                        if endpoint.endswith("/api/chat"):
                            response = requests.post(
                                endpoint,
                                headers={"Content-Type": "application/json"},
                                json=ollama_payload,
                                timeout=int(timeout),
                            )
                            used_backend = "ollama_native"
                        else:
                            response = requests.post(
                                endpoint,
                                headers={"Content-Type": "application/json"},
                                json=openai_payload,
                                timeout=int(timeout),
                            )
                            used_backend = "ollama_openai"

                        if response.status_code == 404:
                            response = None
                            continue
                        break
                    except requests.exceptions.RequestException as e:
                        last_err = e
                        response = None
                        continue

                if response is None:
                    # 两边都不行：给出可操作的提示
                    if not (self.api_key or "").strip():
                        return f"[本地 Ollama 模型未就绪或接口不可用：{ollama_model}（base={self._ollama_base_url()}）]"
                    return "[LLM调用失败：远程不可用且本地 Ollama 未启动]"
            
            print(f"[LLM] 响应状态码: {response.status_code}")
            
            if response.status_code != 200:
                error_detail = response.text[:1000] if response.text else "无详细信息"
                print(f"[LLM] 错误响应内容: {error_detail}")
                print(f"[LLM] backend={used_backend}, payload: model={payload.get('model')}, messages_count={len(messages)}, temperature={temperature}")
                
                # 根据不同错误码给出提示
                if response.status_code == 400:
                    # 尝试解析错误信息
                    try:
                        error_json = response.json()
                        error_msg = error_json.get("error", {}).get("message", error_detail)
                    except:
                        error_msg = error_detail
                    print(f"[LLM] 400错误详情: {error_msg}")
                    return f"[API参数错误: {error_msg[:100]}]"
                elif response.status_code == 401:
                    return "[API密钥无效或未配置（401）]"
                elif response.status_code == 403:
                    return "[API访问被拒绝，可能是网络限制]"
                elif response.status_code == 429:
                    return "[API请求频率过高，请稍后重试]"
                elif response.status_code >= 500:
                    return "[API服务器错误，请稍后重试]"
                return f"[API错误 {response.status_code}]"
                
            result = response.json()

            content = None
            if used_backend in ("ollama_native",):
                content = self._extract_ollama_content(result)
            else:
                content = self._extract_openai_content(result)

            if not content:
                print(f"[LLM] 响应格式异常: {json.dumps(result, ensure_ascii=False)[:500]}")
                return "[API返回格式异常]"

            print(f"[LLM] 成功获取回复，长度: {len(content)}")
            return content
            
        except requests.exceptions.Timeout:
            print("[LLM] 请求超时")
            return "[API请求超时，请重试]"
        except requests.exceptions.ConnectionError as e:
            print(f"[LLM] 连接错误: {str(e)}")
            return f"[无法连接到API服务器: {self.url}]"
        except requests.exceptions.RequestException as e:
            print(f"[LLM] 请求异常: {str(e)}")
            return f"[API调用失败: {str(e)}]"
        except (KeyError, IndexError, json.JSONDecodeError) as e:
            print(f"[LLM] 解析错误: {str(e)}")
            return f"[解析响应失败: {str(e)}]"


# 全局客户端实例
llm_client = LLMClient()
