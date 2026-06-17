"""Minimal tool-using agent. Swap Bedrock <-> Vertex via MONK_MODEL."""

from __future__ import annotations

import os

from langchain.chat_models import init_chat_model
from langchain_core.messages import BaseMessage, HumanMessage, ToolMessage
from langchain_core.tools import tool

DEFAULT_MODEL = "bedrock_converse:openai.gpt-oss-120b-1:0"
MAX_ITERATIONS = 6


@tool
def get_weather(city: str) -> str:
    """Return current weather for a city."""
    return f"It's 28C and sunny in {city}."


@tool
def search_news(topic: str) -> str:
    """Return the top news headline for a topic."""
    return f"Top story on {topic}: AI agents are eating tools."


TOOLS = [get_weather, search_news]
TOOLS_BY_NAME = {t.name: t for t in TOOLS}

model = init_chat_model(os.getenv("MONK_MODEL", DEFAULT_MODEL)).bind_tools(TOOLS)


def agent_run(question: str) -> str:
    messages: list[BaseMessage] = [HumanMessage(content=question)]
    for _ in range(MAX_ITERATIONS):
        ai_msg = model.invoke(messages)
        messages.append(ai_msg)
        if not ai_msg.tool_calls:
            content = ai_msg.content
            return content if isinstance(content, str) else str(content)
        for tc in ai_msg.tool_calls:
            tool_fn = TOOLS_BY_NAME[tc["name"]]
            result = tool_fn.invoke(tc["args"])
            messages.append(ToolMessage(content=str(result), tool_call_id=tc["id"]))
    return "Max iterations reached without a final answer."


if __name__ == "__main__":
    print(agent_run("What is the weather in Bangalore today and what's the latest AI news?"))
