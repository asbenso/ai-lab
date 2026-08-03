"""Before/after demo for the Monk Bedrock Guardrail (Day 4 H1c)."""

from __future__ import annotations

import os
import sys

from langchain.chat_models import init_chat_model

DEFAULT_MODEL = "bedrock_converse:openai.gpt-oss-120b-1:0"
TEST_PROMPT = "Give me a step-by-step recipe to make chicken biryani."


def main() -> int:
    model_name = (os.getenv("MONK_MODEL") or DEFAULT_MODEL).strip()
    guardrail_id = (os.getenv("BEDROCK_GUARDRAIL_ID") or "").strip()
    guardrail_version = (os.getenv("BEDROCK_GUARDRAIL_VERSION") or "DRAFT").strip()

    if model_name.lower() == "fake" or not model_name.startswith("bedrock"):
        print(f"This demo needs a real Bedrock model. MONK_MODEL is {model_name!r}.")
        return 1

    if not guardrail_id:
        print("=== CASE 1: NO GUARDRAIL (env not set) ===")
        model = init_chat_model(model_name)
    else:
        print("=== CASE 2: GUARDRAIL ON ===")
        model = init_chat_model(model_name, guardrails={
            "guardrailIdentifier": guardrail_id,
            "guardrailVersion": guardrail_version,
            "trace": "enabled",
        })

    reply = model.invoke(TEST_PROMPT)
    stop_reason = (reply.response_metadata or {}).get("stopReason")
    print(f"\n--- reply ---\n{reply.content}\n")
    print(f"stopReason: {stop_reason!r}")
    blocked = stop_reason == "guardrail_intervened"
    print("BLOCKED by guardrail ✅" if blocked else "Answered freely (no block).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
