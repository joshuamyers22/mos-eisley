# Security Policy

Security owner: Josh Myers (`joshuamyers22`). Report vulnerabilities privately to
the owner through an existing private channel. Do not include actual secrets or
private source in public issues. This pre-release foundation has no production
support SLA; a response commitment is required before deployment.

The CLI executes no input-supplied commands and is not an OS sandbox. Recorded
commands make no network requests. `openai-run` is the sole live path: it requires
`OPENAI_API_KEY`, a named prompt file and `--allow-data-transfer`; it exposes no
tools and sends `store=false`. Never put API keys in prompt files, arguments, run
directories, issues or logs. Input and artifact parent directories must be
controlled by the user; same-identity processes remain outside the threat model.
See `docs/THREAT_MODEL.md` for scoped guarantees and remaining risks.
