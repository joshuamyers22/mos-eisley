# ADR 0001: Recorded review as the first walking skeleton

Date: 2026-09-05. Status: implemented for the initial milestone.

The design review requires proof of review policy before granting machine or
publishing capabilities. Start with recorded inputs and responses, no executable
tools, and no live SDKs. This makes the full orchestration path deterministic and
testable while the high-consequence execution boundary is still unimplemented.

Use the production template's Python CLI archetype, strict Pyright, Ruff, uv,
unittest, CI/release governance and proprietary license. Keep argparse for this
small command surface; Typer/Textual can be adopted when interactive work begins.
Pydantic validates versioned public contracts. Domain models and review logic do
not import providers, file storage, the CLI, or vendor wire types.

Use SQLite only as a disposable index; files are the source of truth. Split finding
category from impact and derive blocking changes in deterministic policy. Preserve
all original findings; dedupe only exact content. Judge input contains no provider
or critic fields and uses stable hash ordering for reproducible fixture tests.
Text may still reveal an author's style; blinding is structural, not anonymity.

The cassette binds responses to both brief identity and exact request bytes. A
successful replay means the recorded pipeline reproduced, not that a live model
would agree. Byte bounds do not substitute for provider-specific token budgets.

Consequences: this milestone validates infrastructure but cannot measure model
quality or review unseen code. Live adapters, privacy policy, token accounting and
per-request journals must precede paid calls. Kernel containment must precede
tools. The original plan's model IDs/prices and platform claims remain unverified
design inputs; they are not shipped as capabilities or defaults.
