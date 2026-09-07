# Milestone 49 adversarial review: OpenAI response encoding

## Disposition

Accepted as a compatibility and diagnostic hardening change after a credentialed
model lookup exposed `APIConnectionError -> DecodingError -> zlib.error` while the
same key and endpoint returned HTTP 200 through an identity-encoded curl request.
The operator evidence proves the local failure shape, not a general provider defect.

## Findings and implemented changes

| Attack or ambiguity | Implemented disposition | Remaining boundary |
| --- | --- | --- |
| Default compression makes a valid response locally undecodable | Force `Accept-Encoding: identity` at the final bounded-client send boundary | OpenAI or an intermediary may ignore the preference |
| A caller silently re-enables gzip or deflate | Override caller and SDK encoding headers immediately before transport dispatch | Trusted code can replace the HTTP client entirely |
| Identity encoding removes the decoded-size defense | Retain both the early content-length check and incremental decoded-byte ceiling | Identity may use more bandwidth before the same decoded ceiling |
| A server ignores identity and returns malformed compressed bytes | Fail closed without retry and record only `response_decode_error` | No response body is retained for deeper provider forensics |
| Better diagnostics leak upstream text or account information | Add a readiness-only fixed detail vocabulary derived from local exception classes | Trusted process memory still contains the SDK exception chain briefly |
| A local decode failure is mistaken for provider rejection | Keep the coarse kind `transport_error` and distinguish only the local decode stage | The receipt still cannot prove whether an intermediary altered bytes |
| Failed schema-1 receipts are rewritten as schema 2 | Never modify old exclusive receipts; new attempts emit schema 2 | External retention is still required to detect deletion or rollback |

## Verification status

Synthetic transports verify that identity is forced even over a caller-supplied
compression header, ignored identity still flows through decoded-size enforcement,
malformed deflate becomes only `response_decode_error`, and no raw body or credential
enters the receipt. Existing compression, size, SDK-error, one-attempt, and authority-
denial tests remain in force. Automated tests make no live provider request.
