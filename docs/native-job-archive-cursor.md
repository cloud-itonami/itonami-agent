# Job archive and cron cursor candidate

The selected-source composition uses Murakumo job output and archive sources
from candidate commit [`53f0efe`](https://github.com/kotoba-lang/murakumo/commit/53f0efe7f55bc1b3c312a9a1ad80855f007e601f)
in [draft PR #594](https://github.com/kotoba-lang/murakumo/pull/594), stacked on
[draft PR #586](https://github.com/kotoba-lang/murakumo/pull/586), which
depends on merged checkpoint sources including
[`d6fbfab`](https://github.com/kotoba-lang/murakumo/commit/d6fbfab289dcfe272121a06b43149251e7651330).
The Murakumo candidate adds checked checkpoint reads, closure verification,
block synchronization and Git configuration refusals. It is not merged;
this document records the source used for the check, not an enforced build pin
or a qualified dependency. Reconcile the exact merged dependency before build.
It derives the job ID and slot from the pinned schedule and current cursor,
checks the proof's node and the schedule's profile/policy, and learns a live
job lease before archiving. The signed receipt's node and epoch must match the
adopted lease, its timestamp must precede that lease's deadline, and its v2
lease digest must match the full canonical adopted lease. After the private GitHub archive independently
reads back and revalidates the signed checkpoint and output proof, it learns
the same live lease again and checks that the schedule and cursor are unchanged
before attempting the existing durable cursor update. An unknown result is
not permission to retry or advance; a surviving cursor intent requires the
existing explicit reconciliation path.

The separate opt-in `cron-job-archive-head-cursor-main` additionally takes an
independently trusted expected Git commit at argument 24. After the output
archive has been verified and the lease rechecked, it invokes the candidate
GitHub expected-head CAS, checks the fetched head receipt, then learns the
same live lease again and rechecks the schedule and cursor before advancing.
The CAS implementation re-verifies the archive in its own private child work
directory. The earlier `cron-job-archive-cursor-main` retains its existing
non-head path. The host must provision the initial head and pin the exact
expected commit; neither a GitHub ref nor the expected OID is a lease.

Before the CAS the candidate writes and syncs `cursor.head-intent`, recording
the expected head, checkpoint, job, prior cursor, task digest and slot. After
the cursor advances, it moves the marker to `cursor.head-last` and syncs the
directory. A surviving or unreadable intent blocks the cursor planning,
standalone cursor recovery/advance and archive coordinator entries. The head
may advance even if the final lease check, cursor write, marker finalization
or process fails: the host must quarantine the work and independently
reconcile GitHub head/archive and the local cursor, without automatic retry.

The separate opt-in `cron-guarded-job-node-main` takes a host-selected cursor
path at argument 24, checks all four marker names, independently reads the
schedule and cursor, and compares the due slot's previous cursor against the
job arguments. It validates the source and wrapper before journaling, then
requires both source and wrapper strings to round-trip to the exact bytes.
It passes the verified wrapper to the node rather than rereading its path
without a size limit. The node still checks the wrapper against the pinned CID.
Invalid UTF-8 may trap at conversion; no runtime behavior has been
qualified. The original
job-node entry remains callable and does not read the marker. These checks are
not atomic with dispatch; the trusted host must hold serialization throughout
the check and workload lifetime and refuse alternate entries while an outcome
is unknown. A marker's absence after an uncertain write is not proof of
outcome. CAS and lease checks are not atomic: this adds head concurrency
control, not a receiver-side fence or external-effect protection.

An additional opt-in `cron-serialized-job-node-main` takes a private,
pre-provisioned lock path at argument 25, checks that it is a mode-0600 regular
file disjoint from the cursor, input paths and attempt tree, and makes one
non-retrying flock attempt. It holds that cooperative local lock while invoking
the guarded job entry, first syncing `cursor.turn-intent` with the pinned
schedule, previous cursor, job, due slot and hashes of the lock path, token
path, exact quorum ports string, node name, and signer DID. It rechecks the
signer derived from the key before dispatch, requires captured output and retains
the marker on failure or after job completion.
Planning and other guarded jobs refuse a surviving or unreadable turn marker.

The opt-in `cron-serialized-job-archive-head-cursor-main` takes the same
lock path at argument 25, reacquires it without polling, checks that the turn
marker exactly matches its independently derived schedule, cursor, job, lock
path, token path, quorum ports, node name and expected output signer DID, and
then performs verified archive, head CAS and cursor advancement. The `jti4`
marker rejects older `jti1`, `jti2` and `jti3` markers; a
host must reconcile old or unknown markers, never silently upgrade them.
It retires the head marker and then the turn marker only after the cursor
advances. The host must capture and verify the job output and checkpoint before
calling this entry, and reconcile any unknown result. A failure can leave one
or both markers; no automatic recovery is implemented.

The lock is released between the two entries; the durable marker blocks only
cooperating paths. The host must ensure every caller uses the same stable,
non-aliased lock, exclude unguarded entries and establish ownership and ACL
policy. The node-name hash does not authenticate the machine. The signer hash
is a consistency binding; actual proof verification remains necessary. Path hashes do not bind inodes, token contents, or remote quorum
identity. The parent can die or a child can outlive it, so neither entry provides a qualified process lifetime boundary,
resource governor, distributed lock, sink fence or permission to deploy.

The host supplies and protects all paths, the schedule pin, checkpoint pins,
signer, authenticated quorum token, node identity, and a fresh archive work
path. It must serialize all writers across hosts and hold exclusive ownership
of the local files throughout. The two lease checks are not atomic with the
cursor write and do not supply receiver-side fencing; do not deploy this
candidate until an actual distributed writer fence, workload lifetime and
resource governor are qualified. This does not establish that a failed or
unknown cell had no external effects.
The signature binds the digest to the receipt; producing that receipt under a
live lease and enforcing effects against it still require runtime qualification.

Selected current gateway, guarded/serialized job, checkpoint, archive and head-CAS
functions and decision cases passed Amu source check with historical dependencies. The decision tests,
full dependency closure, native runtime, GitHub call, crash recovery and
cross-host serialization have not been executed for this composition.

On one Mac, `test/native/cron_lock_provider_probe.py` exercised an earlier,
externally supplied SHA-pinned Darwin bridge-lock diagnostic. While a separate
process held its task-owned flock, the fixture returned `bridge/local-writer-busy`;
a mutant that skipped acquisition ran its stub command. After release the
fixture reached the stub command. This checks the old diagnostic's local lock
interaction only: it does not execute either new serialized entry, the journal,
a real child workload, process-death recovery, another host or a governor.
