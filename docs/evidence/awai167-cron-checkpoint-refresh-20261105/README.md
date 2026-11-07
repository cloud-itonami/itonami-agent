# Current cron and checkpoint source composition

On 2026-11-05, refreshed a selected historical unity with 195 actual function
forms from this checkout at `156bafa8b5fe8167790c3842fca7c9aa23e2b7f7`
and Murakumo checkpoint draft #594 at
`b7c301c842e6f262d528d8a3a15e398e7919a4fe`. The Murakumo selection includes
current `jo-put` and `cp-empty-readable?`, the checkpoint, job-output,
archive, GitHub head and job-node components, and selected key/token helpers;
the Itonami selection includes cursor, guarded job-node, archive-cursor and
three decision-case definitions. Each selected function was compared back to
its checkout. The previous historical unity supplied remaining dependencies;
this is not a complete pinned source closure.

The pinned Darwin diagnostic compiler returned `ok` on the composed source.
A native fixture executing the three decision-case functions returned zero;
a mutant disabling the pending-marker refusal returned nonzero. The composed
source SHA-256 was
`751bdf40276f2323d17260f1106bb32a1337393258ef9bdf06519a69faa3c1fc`;
the native case fixture SHA-256 was
`9ddd1b4846574815085e5bbe162c944756680bf5790981fe22f4067f5f4510ef`.
The compiler and diagnostic FS2 packager were pinned by SHA-256 to
`920954769b8fdc51cf50dfcab5c44a4e56cf01f261806a153b21488ba81ac4e6`
and `f726f9dd8a4f169187275797a74d55ad3c62cc5f681cd31f19e1a28d67834f8d`.
Processes had a three-second CPU cap; no hard memory cap was used.

`check.py` SHA-256
`dc2952f4e59c70b3eff31a7a7a907c358d00959f5abad7ec239c255bdd5725b8`
uses local absolute paths and a historical unity pinned at
`05c50d38bb0e6c92981d942443008eb8a56a2d84ebf045e54b9030c1c30a1cc9`.
It is diagnostic scaffolding, not a release or deployment command. The pure
decision cases do not execute `jo-put`, the live cron, GitHub, lease, workload
or bot. The empty-output guard has separate evidence in Murakumo #594. A
complete merged and pinned runtime, filesystem provider, governor and
cross-repository end-to-end test remain required.

After Murakumo #594 merged its dependency branch into head
`2b9484698d3c713c76acab80daa6e0acfb773104`, the same diagnostic was rerun
against the unchanged Itonami code. It refreshed and compared 197 selected
functions, including the dependency's two metadata helpers. The compiler
check and native decision cases passed; the pending-guard mutant was detected.
The composed source SHA-256 was
`346a166ef98fdb5ad5d6b0e8e973da804313b97d0e1211e33f1760ea7f19cd34`,
and native case fixture SHA-256 was
`1e0e57982988c30231da853937180399e12c4e3bdd88ae14f9da1e06ab6bb97a`.
The limitations above still apply; the test does not execute GitHub or a bot.
