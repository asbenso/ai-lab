<!-- source: https://docs.aws.amazon.com/bedrock/latest/userguide/what-is-bedrock.html -->

# What is Amazon Bedrock

Amazon Bedrock is a fully managed service that offers a choice of high-performing foundation models (FMs) from leading AI companies through a single API. It also provides a broad set of capabilities you need to build generative AI applications with security, privacy, and responsible AI.

## Models

Bedrock supports models from Anthropic (Claude), Meta (Llama), Mistral AI, Cohere, Stability AI, Amazon (Titan), and OpenAI (gpt-oss). Models are invoked via the unified Converse API for chat-style use or InvokeModel for embeddings and other modes.

## Knowledge Bases

Bedrock Knowledge Bases is a managed RAG pipeline. You point it at a data source in S3, choose an embeddings model, and a managed vector store (or your own OpenSearch). At query time, Bedrock retrieves relevant chunks and either returns the citations or generates a grounded answer.

## Guardrails

Bedrock Guardrails apply content filters, denied topics, and PII redaction to model inputs and outputs. Guardrails are configured once and attached to any model call via the `guardrailIdentifier` parameter.

## Agents

Bedrock Agents orchestrate multi-step task completion. They combine an FM, a set of tools, and optional knowledge bases. AgentCore Runtime is the managed deployment surface for custom LangGraph/Strands agents.
