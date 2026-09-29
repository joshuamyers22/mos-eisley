# Real initial-child candidate test

The real initial child produced integrated commit
`d7237f5e8faf98322c5a3e330b40c674b1f1ac55`, with a separately signed
VCS record. The fresh frozen reviewer package was rebound to this commit and to
the immutable G4 image. New known-good and known-bad runs in that image
validated the reviewer suite; their control record is
`e7cacc707f123c0fc46534b66262b3532aaa86930b18b9859adda00e0f94f77e`.

The candidate gate requires a fresh creator signature for one exact offline
reviewer-test request. Before admission it replays the paid child and VCS chain,
the current clean integrated Git tree, the implementation binding and both
controls. It consumes a private one-use claim before running the test in the
no-network worker, then rechecks source and package bytes. A passing candidate
receipt grants no final whole-suite run, review or acceptance.
