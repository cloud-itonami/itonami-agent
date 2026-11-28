# macOS arm64 turn preflight

The preflight verifies the exact `awai-hiring-ops` profile snapshot at
`$ITONAMI_DIR/profiles/awai-hiring-ops/itonami.edn`. The Kotoba guest reads
the file through the Amu KFR1 capability rooted at the directory on FD 3
and checks its SHA-256 with the pinned Amu implementation. `ITONAMI_DIR`
defaults to `$HOME/.itonami`. An intentional profile change requires review
and an updated digest, byte count, and reproducible guest pin.

## Build and check on Apple Silicon

Run from the Itonami repository with `git` and the macOS command-line tools.
The gate uses a copy of the public profile in an isolated store.

```sh
scratch=$(mktemp -d)
git init "$scratch/amu"
git -C "$scratch/amu" fetch --depth=1 https://github.com/kotoba-lang/amu.git \
  87ec570aff47a0a21b4876fcda4fa9d4e3b934fb
git -C "$scratch/amu" checkout --detach FETCH_HEAD
bin/check-macos-turn-preflight "$scratch/amu" "$scratch/gate"
ITONAMI_DIR="$PWD/itonami" "$scratch/gate/first/bin/itonami-agent" turn preflight awai-hiring-ops
```

For a package build only, use `bin/build-macos-turn-preflight` with the same
two arguments and a fresh output directory. Each build records the Itonami
and Amu revisions and the SHA-256 values of the launcher, Mach-O, source,
compiler and packager in `build-receipt.txt`. The pinned Amu CLI takes a KSL2
source lock and selects `amu-command-fs35`. The gate compares two builds byte
for byte and runs the staged launcher against positive and negative cases.

Preflight exit `0` means the profile byte pin matched. Exit `2` covers an
invalid profile selection, unavailable store or a mismatched file. A missing
or altered guest exits `78`. `turn` and `turn-loop` exit `78` before a provider
call. Preflight has zero model calls, zero tool calls, and no draft output.

## Native turn dependency

The original preflight pin produced the observations below. A newer immutable
Amu adapter candidate now covers [the dedicated Hiring QA route](macos-hiring-qa.md).

At the pinned Amu revision, both upstream `seed/tests/llm-v1-checker.kotoba`
and `seed/tests/llm-v1-ref-checker.kotoba` pass the native checker. Three
incompatible type variants fail with `E2115`. Both accepted fixtures fail
compilation with `E3004` and produce no artifact for each of `aarch64-macos`
and `x86_64-aiueos-user-v3`. Reproduce with the upstream
`scripts/seed/check_llm_v1_checker_macos.py` observer, the pinned
`amu-full-root.macho` and the compiler SHA-256 from the build receipt.

The shared blocker is nominal wire-11 lowering in `seed/30-lower.kotoba`.
The canonical kit describes a synchronous request and a completion or error
with nested usage values. Amu needs to marshal those types and carry an
explicit provider grant in the Darwin Mach-O runtime. The AIUEOS ELF target
has its own CPL3 grant and transport work. Follow [Amu #1901](https://github.com/kotoba-lang/amu/issues/1901)
and [Murakumo #717](https://github.com/kotoba-lang/murakumo/issues/717).

## Hiring QA handoff

A live QA run requires a qualified Darwin wire-11 provider, a governed local
listener with a pinned endpoint and model identity, and an approved synthetic
draft request. The current preflight checks the profile snapshot. Effective
endpoint, model, authorization and budget checks belong to the live turn.
The first draft-only turn can use one synchronous generation with an empty
tool allowlist. The Agent owns the tool, approval, deadline and token checks.

For the eventual QA import, retain the exact UTF-8 draft body and a matching
turn receipt. Bind run ID, profile ID and digest, input and output SHA-256,
Agent and provider revisions and artifact digests, exact model identity and
weights digest, effective endpoint-policy digest, result and finish reason,
observed usage, and the approval reference. Use trusted local artifact
evidence for the model weights. Feed the body and receipt through the app's
ordinary import and approval path, verify persistence after reload, and
compare the export's body SHA-256 to the approved draft. Preflight success
alone leaves the Hiring QA run blocked.
