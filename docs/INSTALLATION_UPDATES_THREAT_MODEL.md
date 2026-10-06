# Installation and update threat model

Scope: release feed, bootstrap, standalone archives, npm/Homebrew adapters and local transactions (plan §§28–29). Owner: Joshua Myers; date: 2026-10-06. Release approval remains accountable owner review.

Assets: executable integrity; current runnable version; credentials/configuration; immutable session/spend evidence. Actors: publisher, local owner, package manager, untrusted repository/model text and network peer.

| Abuse/failure | Controls | Acceptance evidence |
|---|---|---|
| Forged release, channel/platform substitution | Pinned Ed25519 publisher key; exact signed metadata; strict platform/channel/schema/version | Wrong-key, altered payload and incompatible metadata tests |
| Redirect/exfiltration or unbounded download | TLS, fixed distribution origins, redirect refusal, finite timeout and byte caps; no workspace/credential request data | Invalid origin, length and download tests |
| Archive traversal, links or special files | Regular files/directories only, relative bounded names, duplicate refusal, expanded-size bound | Malicious archive tests |
| Local foreign/symlink/conflicting install | User-private owned root, no repository policy, managed launcher receipt, no overwrite of foreign commands | Ownership and launcher-conflict tests |
| Concurrent replacement or active sessions | Exclusive transaction lock and shared client lock; staging verification and atomic pointer | Active-client/concurrent tests |
| Interrupted install/restart or corrupt package | Old pointer retained until verified; journal recovery and retained rollback candidate; fsync atomic metadata | Fault injection at transaction boundaries |
| Rollback opens incompatible storage | Release storage compatibility epoch; refuse mismatched rollback; app updater never touches user/session/spend stores | Compatibility/state-hash tests |
| Package manager replaced by unrelated updater | Origin receipt; npm/Homebrew managed updates use fixed owner instructions; no shell from metadata | Manager-origin tests |
| Secret exposure | Private signing key stays outside repo; public key only in source; first launch checks presence, never displays values | Secret scan and setup tests |

Residual: publisher key compromise and same-user executable modification require owner incident response. No cross-platform support claim is made from unit tests. Bootstrap execution trusts the owner-selected pinned HTTPS source; downloaded application metadata/artifacts are additionally signed/hash verified. No study sampling artifacts are touched.
