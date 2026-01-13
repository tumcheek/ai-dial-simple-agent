import json
from collections.abc import Callable
from typing import Any, AsyncIterator, Union

import requests
import aiohttp

from task.models.message import Message
from task.models.role import Role
from task.tools.base import BaseTool

StreamEvent = Union[str, Message]

class DialClient:

    def __init__(
            self,
            endpoint: str,
            deployment_name: str,
            api_key: str,
            tools: list[BaseTool] | None = None
    ):
        #TODO:
        # 1. If not api_key then raise error
        # 2. Add `self.__endpoint` with formatted `endpoint` with model (model=deployment_name):
        #   - f"{endpoint}/openai/deployments/{deployment_name}/chat/completions"
        # 3. Add `self.__api_key`
        # 4. Prepare tools dict where key will be tool name and value will
        # 5. Prepare tools list with tool schemas
        # 6. Optional: print endpoint and tools schemas
        if not api_key:
            raise ValueError("API key is required")
        self.__endpoint = f"{endpoint}/openai/deployments/{deployment_name}/chat/completions"
        self.__api_key = api_key
        self.__tools_dict = {}
        self._tools = []
        if tools:
            for tool in tools:
                self.__tools_dict[tool.name] = tool
                tool_schema = tool.schema
                self._tools.append(tool_schema)
        print(f"DialClient initialized with endpoint: {self.__endpoint}")


    def get_completion(self, messages: list[Message], print_request: bool = True) -> Message:
        #TODO:
        # 1. create `headers` dict with:
        #   - "api-key": self._api_key
        #   - "Content-Type": "application/json"
        # 2. create `request_data` dict with:
        #   - "messages": [msg.to_dict() for msg in messages]
        #   - "tools": self._tools
        # 3. Optional: print request (message history)
        # 4. Make POST request (requests) with:
        #   - url=self._endpoint
        #   - headers=headers
        #   - json=request_data
        # 5. If response status code is 200:
        #   - get response as json
        #   - get "choices" from response json
        #   - get first choice
        #   - Optional: print choice
        #   - Get `message` from `choice` and assign to `message_data` variable
        #   - Get `content` from `message` and assign to `content` variable
        #   - Get `tool_calls` from `message` and assign to `tool_calls` variable
        #   - Create `ai_response` Message (with AI role, `content` and `tool_calls`)
        #   - If `choice` `finish_reason` is `tool_calls`:
        #       Yes:
        #           - append `ai_response` to `messages`
        #           - call `_process_tool_calls` with `tool_calls` and assign result to `tool_messages` variable
        #           - add `tool_messages` to `messages` (use `extend` method)
        #           - make recursive call (return `get_completion` with `messages` and `print_request`)
        #       No: return `ai_response` (final assistant response)
        # Otherwise raise exception

        headers = {
            "api-key": self.__api_key,
            "Content-Type": "application/json"
        }
        request_data = {
            "messages": [msg.to_dict() for msg in messages],
            "tools": self._tools
        }
        if print_request:
            print("Request:")
            for msg in messages:
                print(f"{msg.role.value.upper()}: {msg.content}")
            print("-" * 50)
        response = requests.post(
            url=self.__endpoint,
            headers=headers,
            json=request_data
        )
        if response.status_code == 200:
            response_json = response.json()
            choices = response_json.get("choices", [])
            if not choices:
                raise Exception("No choices found in the response")
            choice = choices[0]
            if print_request:
                print(f"Choice:\n{json.dumps(choice, indent=2)}\n{'-'*50}")
            message_data = choice.get("message", {})
            content = message_data.get("content", "")
            tool_calls = message_data.get("tool_calls", [])
            ai_response = Message(
                role=Role.AI,
                content=content,
                tool_calls=tool_calls
            )
            finish_reason = choice.get("finish_reason", "")
            if finish_reason == "tool_calls":
                messages.append(ai_response)
                tool_messages = self._process_tool_calls(tool_calls)
                messages.extend(tool_messages)
                return self.get_completion(messages, print_request)
            return ai_response
        else:
            raise Exception(f"HTTP {response.status_code}: {response.text}")

    async def stream_completion(self, messages: list[Message], on_chunk: Callable[[str], None]) -> Message:
        headers = {
            "api-key": self.__api_key,
            "Content-Type": "application/json"
        }
        request_data = {
            "stream": True,
            "messages": [msg.to_dict() for msg in messages],
            "tools": self._tools
        }

        contents = []
        final_tool_calls = {}
        # NOTE:
        # In this educational version, a new aiohttp.ClientSession is created inside
        # each call to stream_completion / stream_completion_gen, including recursive
        # tool-loop iterations.
        #
        # This is done intentionally to keep the code simple while learning how
        # streaming and tool-calling work.
        #
        # In a production version, the session should be created once (per agent run
        # or per client) and reused across all LLM calls, to avoid creating a new
        # TCP/TLS connection on every tool iteration.
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url=self.__endpoint,
                headers=headers,
                json=request_data
            ) as response:
                if response.status == 200:
                    async for line in response.content:
                        if line.startswith(b'data: '):
                            data = line[len(b'data: '):].strip()
                            if data == b'[DONE]':
                                break
                            chunk = json.loads(data)
                            delta = chunk.get("choices", [])[0].get("delta", {})

                            content = delta.get('content', '')
                            if content:
                                on_chunk(content)
                                contents.append(content)

                            for tool_call in delta.get('tool_calls') or []:
                                index = tool_call.get('index')

                                if index not in final_tool_calls:
                                    final_tool_calls[index] = tool_call
                                    final_tool_calls[index].setdefault("function", {}).setdefault("arguments", "")
                                final_tool_calls[index]["function"]["arguments"] += tool_call.get('function', {}).get('arguments', '')
                    ai_response = Message(role=Role.AI, content=''.join(contents), tool_calls=list(final_tool_calls.values()))
                    messages.append(ai_response)
                    if final_tool_calls:
                        tool_messages = self._process_tool_calls(list(final_tool_calls.values()))
                        messages.extend(tool_messages)
                        return await self.stream_completion(messages, on_chunk)
                    return ai_response
                else:
                    raise Exception(f"HTTP {response.status}: {await response.text()}")

    async def stream_completion_gen(self, messages: list[Message]) -> AsyncIterator[StreamEvent]:
        headers = {
            "api-key": self.__api_key,
            "Content-Type": "application/json"
        }
        request_data = {
            "stream": True,
            "messages": [msg.to_dict() for msg in messages],
            "tools": self._tools
        }

        contents = []
        final_tool_calls = {}
        # NOTE:
        # In this educational version, a new aiohttp.ClientSession is created inside
        # each call to stream_completion / stream_completion_gen, including recursive
        # tool-loop iterations.
        #
        # This is done intentionally to keep the code simple while learning how
        # streaming and tool-calling work.
        #
        # In a production version, the session should be created once (per agent run
        # or per client) and reused across all LLM calls, to avoid creating a new
        # TCP/TLS connection on every tool iteration.
        async with aiohttp.ClientSession() as session:
            async with session.post(
                    url=self.__endpoint,
                    headers=headers,
                    json=request_data
            ) as response:
                if response.status == 200:
                    async for line in response.content:
                        if line.startswith(b'data: '):
                            data = line[len(b'data: '):].strip()
                            if data == b'[DONE]':
                                break
                            chunk = json.loads(data)
                            delta = chunk.get("choices", [])[0].get("delta", {})

                            content = delta.get('content', '')
                            if content:
                                contents.append(content)
                                yield content

                            for tool_call in delta.get('tool_calls') or []:
                                index = tool_call.get('index')

                                if index not in final_tool_calls:
                                    final_tool_calls[index] = tool_call
                                    final_tool_calls[index].setdefault("function", {}).setdefault("arguments", "")
                                final_tool_calls[index]["function"]["arguments"] += tool_call.get('function', {}).get(
                                    'arguments', '')
                    ai_response = Message(role=Role.AI, content=''.join(contents),
                                          tool_calls=list(final_tool_calls.values()))
                    messages.append(ai_response)
                    if final_tool_calls:
                        tool_messages = self._process_tool_calls(list(final_tool_calls.values()))
                        messages.extend(tool_messages)
                        async for chunk in self.stream_completion_gen(messages):
                            yield chunk
                        return
                    yield ai_response
                else:
                    raise Exception(f"HTTP {response.status}: {await response.text()}")

    def _process_tool_calls(self, tool_calls: list[dict[str, Any]]) -> list[Message]:
        """Process tool calls and add results to messages."""
        tool_messages = []
        for tool_call in tool_calls:
            #TODO:
            # 1. Get `id` from `tool_call` and assign to `tool_call_id` variable
            # 2. Get `function` from `tool_call` and assign to `function` variable
            # 3. Get `name` from `function` and assign to `function_name` variable
            # 4. Get `arguments` from `function` as json (json.loads) and assign to `arguments` variable
            # 5. Call `_call_tool` with `function_name` and `arguments`, and assign to `tool_execution_result` variable
            # 6. Append to `tool_messages` Message with:
            #       - role=Role.TOOL
            #       - name=function_name
            #       - tool_call_id=tool_call_id
            #       - content=tool_execution_result
            # 7. print(f"FUNCTION '{function_name}'\n{tool_execution_result}\n{'-'*50}")
            # 8. Return `tool_messages`
            # -----
            # FYI: It is important to provide `tool_call_id` in TOOL Message. By `tool_call_id` LLM make a  relation
            #      between Assistant message `tool_calls[i][id]` and message in history.
            #      In case if no Tool message presented in history (no message at all or with different tool_call_id),
            #      then LLM with answer with Error (that not find tool message with specified id).
            tool_call_id = tool_call.get("id")
            function = tool_call.get("function", {})
            function_name = function.get("name")
            arguments_json = function.get("arguments", "{}")
            arguments = json.loads(arguments_json)
            tool_execution_result = self._call_tool(function_name, arguments)
            tool_messages.append(
                Message(
                    role=Role.TOOL,
                    name=function_name,
                    tool_call_id=tool_call_id,
                    content=tool_execution_result
                )
            )
            print(f"FUNCTION '{function_name}'\n{tool_execution_result}\n{'-'*50}")

            return tool_messages

        return tool_messages

    def _call_tool(self, function_name: str, arguments: dict[str, Any]) -> str:
        #TODO:
        # Get tool from `__tools_dict`, id present then return executed result, otherwise return `f"Unknown function: {function_name}"`
        tool = self.__tools_dict.get(function_name)
        if tool:
            return tool.execute(arguments)
        else:
            return f"Unknown function: {function_name}"
