# Agent workspace policy

Secret plaintext MUST NOT appear in repository files intended for AI agents.

Programs MUST use binding references (e.g. service.llm.chat → secret.openai.default), not raw secret values in workspace configuration.
