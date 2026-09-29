# Real initial-child Git integration

The fresh provider child returned a signed proposal for the approved base
`699f345eeab3a663b8372c01220972af2ab62842`. Its dispatch receipt is
`51e400bc884f14d961c398a4fab7e26fa07756606ee0c691e79678572d293acf`;
the paid production receipt is
`6815432e0475ee8c3606f8335ecc931fd54bf0e4503317605f1bcc7ab5f05a9e`.
The ledger settled 2,322 micro-USD. These receipts authorize no Git write.

`reviewer_initial_integration.py` requires a new creator signature naming both
receipts, the exact base revision, changed path, target worktree and private
integration store. It replays the initial-child signature, offline worker,
provider response, audit and ledger before consuming the one-use integration
claim. Git writes take place in a new detached worktree; the source checkout
stays at the approved base. The resulting commit must have exactly that base as
its sole parent, change only the approved path, and contain exactly the signed
child bytes. A separate VCS signature attests the replayable integration record.

The integration record does not authorize candidate tests, final whole suites,
review, creator acceptance, merge, release or activation. Those remain separate
G4 gates. The disposable integration regression covers exact bytes, the
unchanged original checkout, one-use behavior and tamper rejection. The real
integration still requires Joshua's two exact local signatures.
