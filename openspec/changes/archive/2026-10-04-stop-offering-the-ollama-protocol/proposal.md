## Why

Nothing consumes a connection on the `ollama` protocol (the Ollama-native API). It holds no key to project, so no agent runs on it, and speech-to-text cannot use it. Offering it only invites a connection that does nothing. A local Ollama runtime keeps working over its Anthropic and OpenAI wires, which agents use.

## What Changes

- Creating a connection on the `ollama` protocol, or editing one onto it, is refused with `422 PROVIDER_PROTOCOL_RETIRED`.
- A stored connection that already holds `ollama` stays readable, listed, editable in its other fields and deletable, and reaches no agent; switching an agent onto it is refused with the same code.
- `PROVIDER_INTERNAL_ONLY` is replaced by `PROVIDER_PROTOCOL_RETIRED`.
- The Add provider dialog offers a detected local runtime only the wires it serves to agents; the "Ollama API" option and its copy are removed, and a local runtime needs a detected runtime before Models.
- The docs site describes the protocols as Anthropic, OpenAI and unknown.

## Impact

Specs: provider-switching. Code: the provider service, update and switch operations, the errors and their HTTP mapping, the introspector's default URL, the Add provider dialog. Docs: the providers guide, glossary, FAQ, error codes and the architecture pages, in English and Chinese.
