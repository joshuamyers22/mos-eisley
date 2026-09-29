# Security Policy

Security owner: Josh Myers (`joshuamyers22`). Report vulnerabilities privately to
the owner through an existing private channel. Do not include actual secrets or
private source in public issues. This pre-release foundation has no production
support SLA; a response commitment is required before deployment.

Recorded review and conversation commands use local fixtures. Explicit live paths
now include `openai-run`, model readiness and conformance checks, selected MCP
connections, and separately authorized brokered review or coding-child library
flows. Each path has its own transfer, credential, spending and retention contract;
the qualified private G2 review path is not a public live-review command.
`openai-run` requires `OPENAI_API_KEY`, a named prompt file and
`--allow-data-transfer`; it exposes no tools and sends `store=false`. The CLI is
not an OS sandbox. Never put API keys in prompt files, arguments, run directories,
issues or logs. Input and artifact parent directories must be controlled by the
user; same-identity processes remain outside the threat model. See
`docs/THREAT_MODEL.md` for scoped guarantees and remaining risks.
