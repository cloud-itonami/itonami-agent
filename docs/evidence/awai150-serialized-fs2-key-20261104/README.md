# Serialized cron bounded key diagnostic

The diagnostic Mac runtime trapped on the legacy unframed `cr-read` key path.
The candidate adds a separate FS2-capable `key-seed-fs2` path for serialized
cron and its signer-bound job entry; the legacy key path is retained for other
callers. It checks framed regular-file metadata, requests the first 64 bytes,
checks the exact FS2 response and rechecks metadata. Host-owned exclusive paths
are still required: metadata and range calls are not an atomic snapshot and
a same-size replacement can evade this check.

On jacob, macOS 26.3.1 (a), build 25D771280a, native diagnostic tests with a
public synthetic zero key derived the expected DID. Short, missing and invalid
hex keys were refused; a longer file with a valid 64-byte prefix retained the
legacy prefix behavior. The current serialized guard executed actual schedule,
next-slot, job-ID and consume validation; tampered source was refused, and a
valid synthetic source produced the expected turn-intent and reached a test
job stub. Duplicate turn was refused. A separately built fixture of the actual
job entry (with clock stubbed) rejected a changed signer and short key. The
legacy unframed read continued to trap on this diagnostic runtime. No real key,
lease, bot, GitHub or workload was used.

The selected unity SHA-256 was
`245380c293b1f4d70858b4eb60afc90731c0765d1f29cf1a0d08d12e62872fe8`;
Murakumo cell source SHA-256
`ef49691ccca16406a5e5e0cc1ce41f213ad3b91ef926d338b1e952da3e09be5a`;
job-node source SHA-256
`77f35a9fd974b4e93e1b7e4dfbf1e0f3017bafdf9e7cee12a5621dc933283146`;
Itonami guard source SHA-256
`b0b677c742eacd7d523ffa1bdb1adc8bf43a5c05a24d6ebf55f850eda7cdec3c`;
harness SHA-256
`8ac2a78db727d83c543e1c1d9c285ed16288a6bb46ec530168b384969492066b`.
Current definitions were compared against the unity. The pinned diagnostic
compiler and packager were `920954769b8fdc51cf50dfcab5c44a4e56cf01f261806a153b21488ba81ac4e6`
and `f726f9dd8a4f169187275797a74d55ad3c62cc5f681cd31f19e1a28d67834f8d`.

This is a candidate for a host with FS2 O/E support; older runtimes can trap.
Provider failure, concurrent replacement, real credential custody, full job
execution, crash recovery, host containment and governor remain unqualified.

## Source-injected provider observations

The native key fixture was extended with test-only provider substitutions. It
refused malformed mode, over-range mode, short file metadata, directory kind,
non-numeric block count, extra/trailing metadata fields, a short framed range
reply and a failed metadata recheck. A control removing the mode digit check
accepted synthetic `-0` metadata, confirming that this specific malformed
input is detected by the guard. The valid synthetic key, signer and cron
controls continued to pass.

Extended harness SHA-256:
`fc68a83df09ac6e237094d8bd648142377df10da864f11ea00eabad47446f05e`.
These are source-injected responses in a diagnostic native program, not actual
kernel short reads, metadata races, or adversarial same-size replacement.
A qualified provider and exclusively owned key path remain required.

## Target Mac key and DID samples

The bounded-key and DID diagnostic programs were compiled on jacob with the
same pinned source unity, diagnostic compiler and packager. Their signed image
hashes were included in a manifest with SHA-256
`b79460c7644484e18fedd76f7b1c887ff1fe2391e450a762e3c7cac0ed27682e`.
The manifest, image hashes and strict signatures were checked on naphtali,
benjamin and judah, all Darwin ARM64 build 25G332, over pinned Tailscale SSH.
Each host read a public synthetic zero key, derived the expected DID, refused
short, invalid and missing keys, and accepted the legacy-compatible valid
64-byte prefix in a longer file. Only private task-owned temporary files were
used and removed. Host observer SHA-256:
`677b9f933e2fb2fb2828e2a94fff58365d10d9e6ade8e56d57ec5e31018cc71e`;
local builder SHA-256:
`1b6442598804c5d6a7ef9227bebc233024077b8a4f1e50adc9a63d9671aba8f8`.

These are local diagnostic artifacts, not a rebuilt release runtime. The tests
do not establish real key custody, adversarial replacement resistance, live
job or lease behavior, GPU/resource governance, GitHub or bot operation.

## Synthetic lease token on diagnostic Mac

A later composition refreshed `ln-frame`, `ln-fs`, `ln-exists?`, and
`ln-token` from the current Murakumo checkout; its SHA-256 was
`e6355c6e5e336ccddb334f901a9a887a6be151db91212cfdedf8eb98d4cb1b71`.
The test now checks those functions, their immediate token helpers, and the
job entry against that checkout before compiling. With a disposable synthetic
token, the real `lease-token` returned the trimmed token; short and missing
files did not match. The actual job entry, with a fixed diagnostic clock and
an intentionally wrong expected signer, returned `job/signer-changed` with
the token path set. This establishes neither authenticated lease traffic nor
workload dispatch, and the diagnostic runtime is not a production host.

## Bounded lease-token candidate

Murakumo commit `c657785` adds `lease-token-bounded` and selects it when the
job entry receives the serialized guard's expected signer. Itonami's
serialized archive/head/cursor entry uses the same bounded token path; the
older nonserialized entries retain `lease-token`. The new path rejects files
outside 32–4096 bytes, nonregular or malformed metadata, unexpected response
length, changed metadata, and tokens shorter than 32 bytes after trimming.
The host must own the path and prevent replacement or same-size writes during
reads. Providers that cannot support the required FS2 operations may refuse
or trap; the size cap can reject previously accepted long tokens.

On the diagnostic Mac, current composed source SHA-256
`d8cadbebdd8312b265053d2103a983cb7afc13e73a479ef6165395752952c03f`
passed the pinned compiler's `check`; the source-bound native test passed a
synthetic normal token, a 4096-byte token, and refusal of a 4097-byte file,
short token, whitespace-only token and missing file. The real job-entry
fixture with its fixed clock and a deliberately wrong signer returned the
expected signer refusal with a synthetic token path set. The archive entry was
source-checked but was not executed in this test. Fault-injected malformed FS2
responses, actual authenticated leases, GitHub storage, workload execution,
production runtime and the governor are not qualified by these observations.

### Token read fault injection

The same source-bound diagnostic on the Mac was extended with source-injected
faults. A range request shortened by one byte was refused, while a mutant
with the returned-length guard removed accepted the resulting synthetic
32-byte token. Forcing the metadata recheck to disagree also refused. Injected
metadata cases refused empty, negative, out-of-range mode, too-small or too-large
size, nonnumeric blocks, nonregular kind, extra fields and trailing space;
a well-formed injected metadata control succeeded. These are controlled source
mutations, not kernel or provider fault injection, and do not qualify the
archive execution path or a production FS2 provider.
