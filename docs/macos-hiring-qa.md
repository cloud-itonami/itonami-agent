# macOS arm64 Hiring QA turn

`itonami-agent turn hiring-qa` selects `awai-hiring-ops` from `ITONAMI_DIR`
using the native profile preflight. The package contains a fixed fictional
request and a signed Kotoba guest built with KSL2. The native Amu broker
admits one synchronous wire-11 generation for `inkling-2-mini-gyomu-qa`
through `murakumo-qa-v1`. An independently signed deadline of 1–90 seconds
applies only to this route. It reserves 96 output tokens and exposes zero
tools. The guest requires a complete
`stop` result with bounded UTF-8 text and observed usage. A finish reason of
`length` or reported input usage above 512 tokens refuses the draft.

## Build and run the synthetic gate

Run on Apple Silicon from this checkout. The first compiler pin builds the
independent profile preflight. The adapter pin supplies the signed native
launcher, compiler and packager for Hiring QA. The build verifies their
digests and signatures before execution. The gate uses Python and Basilisp
0.5.1 to stage Amu's fixture, generate ephemeral test authority in memory,
and count requests. The Agent invocation itself uses the same package route
as an approved turn.

```sh
work=$(mktemp -d)
git init "$work/preflight-amu"
git -C "$work/preflight-amu" fetch --depth=1 https://github.com/kotoba-lang/amu.git \
  87ec570aff47a0a21b4876fcda4fa9d4e3b934fb
git -C "$work/preflight-amu" checkout --detach FETCH_HEAD
bin/build-macos-turn-preflight "$work/preflight-amu" "$work/preflight"

git init "$work/adapter-amu"
git -C "$work/adapter-amu" fetch --depth=1 https://github.com/kotoba-lang/amu.git \
  8429fd79ae71a3fe4a27487b87dfe0325f3a1035
git -C "$work/adapter-amu" checkout --detach FETCH_HEAD
test/native/check_macos_hiring_qa.py "$work/adapter-amu" "$work/preflight" "$work/gate"
```

The gate's anonymous FD4 supplies a synthetic bearer to the native host.
The listener is a local fixture that returns a known fictional draft. The
gate verifies its UTF-8 bytes, finish reason and usage, then verifies refusal
and counts HTTP requests for altered authority, budget, model and response
cases. The fixture defaults to 12 seconds. It also checks a one-second
timeout and a response delayed past 15 seconds under a signed 25-second
grant. `completion/result/receipt.json` records the result as synthetic.
See the [pinned Amu adapter and fixture contract](https://github.com/kotoba-lang/amu/blob/8429fd79ae71a3fe4a27487b87dfe0325f3a1035/docs/native-llm-wire-v1.md).

## Approved deployment and invocation

The package built by `bin/build-macos-hiring-qa` has no registration and
refuses before inference. The operational deployment requires an authorized
registration build, a protected QA listener and backend, an issuer with the
approved caller identity and expiry, and an independently signed run approval.
Node Ops must provide the resident and model-weight SHA-256, exact loopback
endpoint, observed direct-backend access denial, and the issuer's public
verification key. Keep the resident and backend provenance with the QA run.
Measure complete draft latency through the governed listener within the
signed deadline during live QA. A first-token timing covers a different
part of the turn.

After approval, follow the pinned Amu registration boundary to set `mm-port`
and `mm-credential` in a separate reviewed Amu checkout. Build the registered
launcher with the pinned native compiler and packager:

```sh
bin/build-macos-hiring-qa "$work/adapter-amu" "$work/preflight" "$work/package"
registered="$(mktemp -d)/registered"
(cd "$AUTHORIZED_AMU_CHECKOUT" &&
  basilisp run -p scripts/seed scripts/seed/build-macos-cli.cljc -- --output "$registered")
codesign --verify --strict "$registered/amu-cli.macho"
shasum -a 256 "$registered/amu-cli.macho" \
  "$work/package/hiring-qa/amu/amu-full-root.macho" \
  "$work/package/hiring-qa/amu/kotoba-packager-root.macho"
```

The deployment operator installs the registered `amu-cli.macho` under
`hiring-qa/amu/` in the package and adds `hiring-qa/approval-key.pem` and
`hiring-qa/registration.json`. The package and its ancestors must be
root-owned and protected from group and world writes. The runtime checks
the launcher and issuer key against the registration. Registration JSON
uses these fields:

| Field | Required value |
|---|---|
| `schema`, `mode` | `itonami.hiring-qa-registration.v1`, `approved` |
| `issuer`, `keySha256` | Approved issuer ID and SHA-256 of its PEM public key |
| `port`, `launcherSha256` | Exact approved IPv4 loopback port and signed registered launcher SHA-256 |
| `residentSha256`, `weightsSha256` | Verified resident bundle and model weights SHA-256 |

The issuer supplies an LF-terminated canonical KLG1 grant and a detached
signature over the exact approval JSON bytes (OpenSSL SHA-256 verification).
The grant binds the guest SHA-256, wire and schema, runtime profile, exact
provider, origin and model, deadline and token budget. The approval supplies
`schema` (`itonami.hiring-qa-approval.v1`), `decision` (`approve`), a fresh
32-character lowercase hex `run`, `profile`, `profileSha256`, `buildSha256`
of `hiring-qa/build.json`, `policySha256` of `registration.json`,
`grantSha256`, and integer Unix `expiresAt`. The expiry must cover the
granted deadline and lie within 15 minutes. The Agent consumes the run ID in
the local Itonami store before provider dispatch. The approved launch closes
FD4 and uses the issuer built into the registered native host.

```sh
ITONAMI_DIR="$ITONAMI_STORE" "$INSTALLED_PACKAGE/bin/itonami-agent" \
  turn hiring-qa awai-hiring-ops "$ISSUED_KLG1" "$ISSUED_APPROVAL" "$ISSUED_SIGNATURE" "$NEW_RESULT_DIR"
```

## Hiring handoff

Keep `receipt.json` alongside the exact `draft.txt` and `draft.edn` files.
The receipt binds run, source lock and module digests, profile and input,
candidate and registered runtime identities, approval and KLG1 digests,
endpoint policy and model, and the actual result, usage and draft SHA-256.
Use a completed `pass` receipt and confirm its draft digest before import.
Refusals before broker invocation leave no draft, and native refusals after
admission record a classified result with no draft.

Hiring's normal import expects the `awai.hiring-draft/1` EDN and exact
UTF-8 TXT. The separate JSON receipt is QA evidence. The generated EDN
marks Recruit review unverified. The offline Hiring domain import accepted
the bundle and verified its exact body, while rejecting the changed body
and disallowing approval when the body or Recruit review was missing.
For live QA, complete the independent Hire/Recruit checks before approving,
then reload and verify the approved export digest against the native draft.
