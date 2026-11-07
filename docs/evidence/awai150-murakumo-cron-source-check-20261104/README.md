# Murakumo and Itonami selected source composition

On 2026-11-04, a selected historical unity source was refreshed with all 147
function definitions from the current Murakumo checkpoint, job output,
archive, GitHub archive, head, GraphQL head and job-node sources at commit
`f2e38a81fa4b1423f3ec8c494885308e0e2148e0`. All 36 functions from the
Itonami cursor, guarded job-node and archive-cursor sources at commit
`889a1a6b5e433154ebe854ff37b4d9b06cb036e6` were present and matched their
source definitions. The existing Amu CLI `check` returned `ok`.

The input historical unity SHA-256 was
`b09336a24a7265180fd8306eaafb9c2ba7470e8fa7608694ee748e07c35b00d4`;
the refreshed unity SHA-256 was
`05c50d38bb0e6c92981d942443008eb8a56a2d84ebf045e54b9030c1c30a1cc9`.
The one-off assembler had SHA-256
`6965d320ccaafbc19a6b638647f42fd6121b89c89919da34864937c9dc967cbf`;
its output path was changed for this run. The current archive source SHA-256
was `a5e8808cd21e2d68f3b79e9ed74f7ec1919805532db61f8ecd9403ab2d74846e`.
The unity and assembler were local staging artifacts and are not an enforced
source lock or a reproducible release build.

This validates selected source composition only. It did not run the Itonami
cases, compiler-generated native program, actual GitHub operations, fault or
crash recovery, production provider, host containment, a model, or bots. The
final merged cross-repository closure must be pinned and verified independently.

## Native pure decision cases

On jacob, macOS 26.3.1 (a), build 25D771280a, the selected unity above was
compiled with the pinned diagnostic Mac compiler and packaged with the pinned
FS2 diagnostic packager. The three current cursor, guarded-node and
archive-cursor case functions ran and returned exit 0. A separately built
mutant removing the pending-state refusal returned exit 1. The harness checks
that each test function in the unity exactly matches its current checkout.

The native fixture source SHA-256 was
`576b6bb17ec867b5316537d2244bf4573b7d3a970e8f3c25eb6ee8906ede21fc`;
the harness SHA-256 was
`931e1420db177f16a1f957536207da7910f2c12a2885464a3831aca58dcf6b86`.
The diagnostic compiler and packager SHA-256 values were
`920954769b8fdc51cf50dfcab5c44a4e56cf01f261806a153b21488ba81ac4e6` and
`f726f9dd8a4f169187275797a74d55ad3c62cc5f681cd31f19e1a28d67834f8d`.
These are pure decision cases. No filesystem provider, lease, signed workload,
GitHub transaction, crash recovery, bot or resource governor was exercised.

## Native bounded cursor reads

On the same Mac, a source-bound fixture used the current `cc-read-bounded`
function and the matching pinned Murakumo checkpoint read functions through a
signed diagnostic FS2 runtime. It accepted the small input and the 1024-byte
cursor and 8192-byte definition limits, and returned no bytes for the
1025-byte and 8193-byte over-limit files, an empty file and a missing file. A
separately compiled variant with the size limit removed failed the cases.
All files were in a fresh private FD3 scope.

Cursor source SHA-256:
`bae632993f616879aead22792d7a2015992a17f2e1cdb9f3f6ee15de7795797c`;
case source:
`9bdfedfe9bb96e5d5d3d2e9702817c33bf112f3ddbedbed0ae1c54b5de18bcff`;
fixture source:
`59230acc78916e87b282713c3ccfb0a1760090d9d78847e8858ba04a84ce6a5b`;
harness:
`96a4a34e1271b0bc0df0b22bfa402d709f22d1378132bb3a78156f51b5d964e7`.
The unity, checkpoint, compiler and diagnostic packager pins are the same as
above and in the associated harness invocation. This is one local provider
sample, not short-read fault injection, metadata-race or provider qualification,
actual cron dispatch, GitHub publication, crash recovery or a governor.

## Native cursor advance and reconciliation

On the same Mac, the current source-bound cursor and pinned checkpoint FS2
functions executed against fresh private files. A successful advance produced
the expected cursor and independently computed old/new CID intent in `.last`.
A changed cursor and existing pending file were refused without overwriting
their original files. A completed replacement with an exact intent was
reconciled; old cursor, pending file and malformed intent remained
`cursor/recovery-unknown`, with their intents retained.

Fixture source SHA-256:
`b2eca64bcfd19c0788a192217cd993d99665860aa76defc85f4a05929ef7fcd2`;
harness SHA-256:
`933b03e573683cde45d66d3a483163c75a0eaf9c13c99713ce7ee4acd4a94ba3`.
The unity, component, compiler and diagnostic packager pins are as above.
This is a local exclusive synthetic FS2 test, not a host lock, process-kill or
power-loss test, live GitHub archive, lease check, bot run or governor gate.

## Cursor process-death observations

The current cursor advance was compiled with five test-only output-pipe pause
points. On the same Mac, the observer checked the cursor, intent, pending and
archive files, then SIGKILLed only the child it started. The uninstrumented
fixture returned `cursor/recovery-unknown` after intent sync or pending write;
after cursor rename or directory sync it reconciled as `cursor/recovered`.
After intent archival, it returned `cursor/recovery-unknown` because the
intent was gone. In every case the old or new cursor bytes remained as
expected. The caller must still reconcile the independently archived workload;
a recovered cursor alone is not permission to run it again.

Extended harness SHA-256:
`b13eb36bf4abeb2689b81cb44e84f806a2b6af95e836ed156ec75cf9725e729b`.
This is one source-instrumented process-kill sample per boundary on a local
diagnostic provider. It does not prove power-loss durability, actual I/O
faults, concurrent locking, GitHub behavior, whole-workload termination or
resource governor qualification.

## Native turn-intent binding

The extended native diagnostic invoked the current `cc-turn-begin` and
`cc-turn-finalize` through the private FS2 root. An independent host calculation
matched the `jti4` marker's schedule, cursor CID, job, slot and hashes of lock,
token path, port string, node and signer. A second begin while the marker
existed was refused without changing it. Finalization moved the same bytes to
`.turn-last`. The previous cursor and process-death controls also passed.

Extended fixture SHA-256:
`6846a20139dba40ab5a1eda98870d80acdc5d40e1b7ce956634d3d6dc0297732`;
harness SHA-256:
`8d0349a1420964a596b6da2f33168b10b42c5de52041aa4251cd02f7283a445c`.
This establishes one local marker sample, not a lock held across both calls,
authenticated node identity, distributed fencing, complete workload lifetime,
real GitHub publication, or recovery after power loss.

## Serialized entry refusal with native FS2 and flock

The current `cron-serialized-job-node-main`, `cjg-run`, and cursor guard were
executed natively on the same Mac with the diagnostic FS2 provider and an
owned mode-0600 lock. A separate process-held flock returned
`cron-lock/busy-or-unknown`. With an available lock, each of `.pending`,
`.intent`, `.head-intent`, and `.turn-intent` caused its corresponding unknown
refusal without changing the marker or reaching the job stub. An invalid plan
was also refused. A separately built variant with the turn-marker guard
removed fell through to plan refusal, demonstrating that the marker control
is actually exercised. The clock and job body were explicitly stubbed.

Fixture source SHA-256:
`6b178e397ee7abd42019b5939bb53632a22a8928c18787b4d7c70b30a1d6b67a`;
guard source SHA-256:
`99e0e96d0b3f5616d6e092a275d415c04c3842a4e84f5548ee79f253457542d9`;
harness SHA-256:
`6604ece28a4780e4bd5d5cce04a1db1ab6b50aa707c91272fe38ae5bc4aeccdf`.
This tests refusals, not a successful job, actual clock, lease, production
provider, cross-call lock lifetime, child containment, GitHub or a governor.

## Serialized entry with stubbed positive dependencies

The extended native fixture also reached the positive serialized guard path
using an actual private FS2 scope and flock. Before entering the test-only job
stub it wrote a `jti4` turn intent; the stub checked that the marker existed
and received the expected source, input and signer. The host independently
checked the marker's cursor CID and all bound fields. A second invocation with
the marker present returned `cron-guard/turn-intent-unknown` and did not call
the job stub again. The prior refusal controls also passed.

For this positive path, clock, plan/consume validation, next-slot and job-ID
selection, key loading, signer derivation and the job body were replaced by
explicit test stubs. It therefore does not validate a real schedule, key,
lease, workload, output, GitHub archive, cross-call locking or governor.
Positive fixture SHA-256:
`459f54840370e2486efbc26d3ad42eb9c50bcb722368dd078c0f6e22c4c2218c`;
extended harness SHA-256:
`5349a10d47072e1f8ff46a44e4daf193c686611e60bca6a10a333e664e993646`.

## Actual schedule and input validation; key-read limitation

The native serialized-entry diagnostic was extended with a synthetic schedule,
cursor, source and wrapper generated by the actual Kotoba schedule functions.
With the actual plan, next-slot, job-ID and consume validation in place, a
modified source was refused as `consume/source-cid`; the correct source reached
the job stub only after creating the expected `jti4` marker. An independent
host calculation checked the cursor CID and marker bindings, and a duplicate
invocation was refused. Clock, key loading, signer derivation and the job body
were stubbed for this successful path; no real lease or workload ran.

An attempt with the actual `key-seed` and signer functions using a synthetic
all-zero key terminated with SIGTRAP on the diagnostic Mac runtime. A separate
native fixture calling the current `cr-read` alone on that synthetic file also
terminated with SIGTRAP. The `cr-read` and `key-seed` bodies were independently
compared to the current Murakumo `fleet_cell_run.kotoba`; this isolates a
reproducible diagnostic runtime/key-read incompatibility, but does not prove
its exact kernel or ABI cause or characterize a release runtime. The file was
synthetic and task-owned. No real secret was read.

Actual-plan fixture SHA-256:
`184225ea5f96f082c0b0c645a48dbe094d39667fa2ef9a7cd0a5a2a734e7cb90`;
key-read probe SHA-256:
`5117175d9dbbc1d2c6103ced1d5b8c4ac8ddf4f8e301e4fb8bc530b1245e07c4`;
Murakumo cell source SHA-256:
`0ea69703d2f5d237a405b6ef98e0b457aa2fbd0d6c7da1a3201e2ddf468a8b0f`;
harness SHA-256:
`24f3b15ddb3ff2e64c9d70c6627a12a140562ac16f6e5aa8c5daa61abe2014e0`.
Neither path qualifies actual credentials, GitHub, lease, workload, crash
recovery, resource governance or production deployment.
