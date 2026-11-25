#!/usr/bin/env python3
"""Orchestrate an Amu-selfhost Linux runtime gate for the Kotoba cron store.

Python only pins inputs, invokes the Amu compiler/KX64 runner, and checks the
receipt. All product behavior runs in the Kotoba artifact on Amu's native
Linux static runtime; no legacy implementation or language runtime is used.
"""

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path


AMU_COMMIT = "87ec570aff47a0a21b4876fcda4fa9d4e3b934fb"
AMU_BINARY_PATH = "bin/amu-linux-x86_64"
AMU_BINARY_SHA256 = "237b61cce51d442aed83ba5006de2828424ed55ef201a622054444179722c812"
AMU_RUNNER_SOURCE = "seed/x86_64-kx64-runner.kotoba"
AMU_RUNNER_SHA256 = "c9f1fe1b5c1748450fb11b233cbdc9d9234880a60dc480c0387b173f60d905be"
AMU_CANDIDATE_SOURCE = "seed/experimental/98-x86_64-project-fs-cli.kotoba"
# Amu's selfhost-native run 45617427645 qualified these experimental
# project-profile digests with F1=F2=F3 and the scoped wire-35 runtime.
AMU_CANDIDATE_COMPILER_SHA256 = "9929a6f6863787b142ce753f8650ab9f410f4176c5110e50cf2d7622749eeee2"
AMU_CANDIDATE_COMPILER_BYTES = 10691072
AMU_CANDIDATE_RUNNER_SHA256 = "57eb22599e420a8d7f5327fd7cf7df8490c27a816f05224c9b14395e090a76e5"
KOTOBA_COMMIT = "14e84d230933e8aa638f3a416c4728d0c305305e"
KOTOBA_JCS_PATH = "lib/org.ietf.jcs/kotoba/jcs/reader.kotoba"
KOTOBA_JCS_SHA256 = "f8af2953904bd0a96e7b5c3b9e34151bcae3754e5358669adb8ac289acc0872f"
KOTOBA_STORE_IO_PATH = "lib/kotoba.hata/src/hata/store_io.kotoba"
KOTOBA_STORE_IO_SHA256 = "25ee164fbdc54360549376c07a8dfa54413db0b00d43562ae77cc89b0031bc3a"

ROOT = Path(__file__).resolve().parents[1]


def sha(data):
    return hashlib.sha256(data).hexdigest()


def git(repo, *args):
    return subprocess.check_output(["git", "-C", str(repo), *args])


def fetch_commit(url, commit, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.mkdir(parents=True, exist_ok=False)
    subprocess.run(["git", "init", "--bare", str(path)], check=True, stdout=subprocess.DEVNULL)
    subprocess.run(["git", "-C", str(path), "remote", "add", "origin", url], check=True)
    subprocess.run(["git", "-C", str(path), "-c", "protocol.version=2", "fetch",
                    "--depth=1", "--filter=blob:none", "origin", commit], check=True)
    actual = git(path, "rev-parse", "FETCH_HEAD").decode().strip()
    if actual != commit:
        raise RuntimeError(f"source revision mismatch: expected {commit}, got {actual}")


def git_blob(repo, commit, path):
    return subprocess.check_output(["git", "-C", str(repo), "show", f"{commit}:{path}"])


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def run(name, argv, cwd, env, calls, timeout=900, allow_stderr=False):
    started = time.monotonic()
    result = subprocess.run(list(map(str, argv)), cwd=cwd, env=env,
                            capture_output=True, timeout=timeout)
    calls.append({"name": name, "exit": result.returncode,
                  "seconds": round(time.monotonic() - started, 3),
                  "stdout_sha256": sha(result.stdout), "stderr_sha256": sha(result.stderr)})
    write(Path(cwd) / f"{name}.stdout", result.stdout)
    write(Path(cwd) / f"{name}.stderr", result.stderr)
    if result.returncode != 0:
        raise RuntimeError(f"{name} failed ({result.returncode}): "
                           f"{result.stderr.decode(errors='replace')[-2000:]}")
    if result.stderr and not allow_stderr:
        raise RuntimeError(f"{name} wrote stderr: {result.stderr.decode(errors='replace')[-2000:]}")
    return result.stdout


def derive_project_compiler(baseline, amu_repo, out, env, calls):
    manifest = git_blob(amu_repo, AMU_COMMIT, "seed/FULL-MANIFEST").decode("ascii")
    modules = [line for line in manifest.splitlines() if line and not line.startswith("#")]
    if len(modules) != 61 or "seed/98-x86_64-project.kotoba" not in modules:
        raise RuntimeError("pinned Amu FULL-MANIFEST does not match the 61-source candidate")
    sources = out / "amu-full-candidate.kotoba"
    with sources.open("wb") as stream:
        for module in modules:
            path = AMU_CANDIDATE_SOURCE if module == "seed/98-x86_64-project.kotoba" else module
            stream.write(git_blob(amu_repo, AMU_COMMIT, path))
            stream.write(b"\n")

    compiler = baseline
    generations = []
    for index in (1, 2, 3):
        image = out / f"amu-candidate-F{index}.elf"
        run(f"derive-amu-F{index}", [compiler, "compile", sources, "--target", "x86_64-linux",
            "--output", image, "--format", "static"], out, env, calls, timeout=900)
        image.chmod(0o700)
        image_bytes = image.read_bytes()
        generations.append({"sha256": sha(image_bytes), "bytes": len(image_bytes)})
        compiler = image
    if generations[0] != generations[1] or generations[1] != generations[2]:
        raise RuntimeError(f"Amu full-source derivation did not reach a fixed point: {generations}")
    if AMU_CANDIDATE_COMPILER_SHA256 and generations[-1] != {
            "sha256": AMU_CANDIDATE_COMPILER_SHA256,
            "bytes": AMU_CANDIDATE_COMPILER_BYTES}:
        raise RuntimeError(f"Amu candidate compiler differs from qualified digest: {generations[-1]}")
    return compiler, generations, sha(sources.read_bytes())


def locked_project(out, kotoba_repo):
    sources = out / "src"
    for directory in ("agent_cli", "hata", "itonami", "jcs"):
        (sources / directory).mkdir(parents=True, exist_ok=True)
    cli = sources / "agent_cli/cron_jobs_store_cli.kotoba"
    store_io = sources / "hata/store_io.kotoba"
    jobs = sources / "itonami/cron_jobs_json.kotoba"
    store = sources / "itonami/cron_jobs_store.kotoba"
    schedule = sources / "itonami/schedule.kotoba"
    pause_marker = sources / "itonami/pause_marker.kotoba"
    jcs = sources / "jcs/reader.kotoba"
    shutil.copy2(ROOT / "kotoba/agent_cli/cron_jobs_store_cli.kotoba", cli)
    shutil.copy2(ROOT / "kotoba/itonami/cron_jobs_json.kotoba", jobs)
    shutil.copy2(ROOT / "kotoba/itonami/cron_jobs_store.kotoba", store)
    shutil.copy2(ROOT / "kotoba/itonami/schedule.kotoba", schedule)
    shutil.copy2(ROOT / "kotoba/itonami/pause_marker.kotoba", pause_marker)
    write(jcs, git_blob(kotoba_repo, KOTOBA_COMMIT, KOTOBA_JCS_PATH))
    write(store_io, git_blob(kotoba_repo, KOTOBA_COMMIT, KOTOBA_STORE_IO_PATH))

    modules = [
        ("hata.store-io", store_io),
        ("itonami.cron-jobs-json", jobs),
        ("itonami.cron-jobs-store", store),
        ("itonami.pause-marker", pause_marker),
        ("agent-cli-cron-jobs-store", cli),
        ("itonami.schedule", schedule),
        ("jcs.reader", jcs),
    ]
    modules.sort(key=lambda row: row[0])
    files = sorted([cli, store_io, jobs, store, pause_marker, schedule, jcs], key=lambda p: str(p))
    lock_lines = ["KSL2", f"entry {cli}"]
    lock_lines.extend(f"module {name} {path}" for name, path in modules)
    lock_lines.extend(f"file {sha(path.read_bytes())} {path}" for path in files)
    lock = out / "cron-store.ksl"
    lock.write_text("\n".join(lock_lines) + "\n", encoding="ascii")
    return cli, lock, {str(path): sha(path.read_bytes()) for path in files}


def execute(name, runner, payload, scope, action, value, option, expected_result, out, calls,
            allow_stderr=False, extra1="", extra2=""):
    capabilities = "7,23,35,37,38,39" if action == "create" else "7,35,37,38,39"
    env = {
        "PATH": "/nonexistent",
        "KEXE_ALLOW": capabilities,
        "KEXE_CAP_RESOURCES_35": str(scope),
        "KEXE_STACK_BYTES": "8388608",
        "KEXE_STRUCTURED_REPORT": "1",
    }
    argv = [runner, payload, "0", "0", "x86_64", capabilities, "--",
            action, str(scope / "d"), value, option, extra1, extra2]
    stdout = run(name, argv, out, env, calls, allow_stderr=allow_stderr)
    if not re.search(rb":result " + str(expected_result).encode() + rb"\b", stdout):
        state = {}
        for path in sorted(scope.rglob("*")):
            if path.is_file():
                state[str(path.relative_to(scope))] = path.read_bytes()[:4096].decode(errors="replace")
        raise RuntimeError(f"{name} returned no successful KX64 result: "
                           f"stdout={stdout!r}; stderr={(out / (name + '.stderr')).read_bytes()!r}; "
                           f"scope={state!r}")
    return stdout


def execute_launcher(name, launcher, scope, action, value, option, expected_exit, out, calls,
                    env_overrides=None, extra1="", extra2="", append_empty_option=False):
    env = dict(os.environ)
    env.pop("ITONAMI_CRON_JOBS_RUNNER", None)
    env.pop("ITONAMI_CRON_JOBS_PAYLOAD", None)
    if env_overrides:
        env.update(env_overrides)
    if action in ("pause-global", "resume-global", "status-global"):
        global_root = scope / "itonami"
        global_root.mkdir(parents=True, exist_ok=True)
        env["ITONAMI_DIR"] = str(global_root)
        argv = [launcher, "cron", "jobs", action]
        if action == "pause-global" and value != "":
            argv.append(value)
    else:
        argv = [launcher, "cron", "jobs", action, scope / "d"]
        if value != "":
            argv.append(value)
        if option != "" or append_empty_option:
            argv.append(option)
        if extra1 != "":
            argv.append(extra1)
        if extra2 != "":
            argv.append(extra2)
    started = time.monotonic()
    result = subprocess.run(list(map(str, argv)), cwd=ROOT, env=env,
                            capture_output=True, timeout=120)
    calls.append({"name": name, "exit": result.returncode,
                  "seconds": round(time.monotonic() - started, 3),
                  "stdout_sha256": sha(result.stdout), "stderr_sha256": sha(result.stderr)})
    write(out / f"{name}.stdout", result.stdout)
    write(out / f"{name}.stderr", result.stderr)
    if result.returncode != expected_exit:
        raise RuntimeError(f"{name} launcher exit {result.returncode}, expected {expected_exit}: "
                           f"stdout={result.stdout!r}; stderr={result.stderr!r}")
    if expected_exit == 0 and not re.search(rb":status :ok :result 0\b", result.stdout):
        raise RuntimeError(f"{name} launcher did not report native success: {result.stdout!r}")
    if expected_exit == 1 and not re.search(rb":status :ok :result 1\b", result.stdout):
        raise RuntimeError(f"{name} launcher did not report native refusal: {result.stdout!r}")
    if expected_exit == 2 and not re.search(rb":status :ok :result 2\b", result.stdout):
        raise RuntimeError(f"{name} launcher did not report native input refusal: {result.stdout!r}")
    return result.stdout


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--amu-url", default="https://github.com/kotoba-lang/amu.git")
    parser.add_argument("--kotoba-url", default="https://github.com/kotoba-lang/kotoba.git")
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    amu_repo = out / "inputs/amu"
    kotoba_repo = out / "inputs/kotoba"
    fetch_commit(args.amu_url, AMU_COMMIT, amu_repo)
    fetch_commit(args.kotoba_url, KOTOBA_COMMIT, kotoba_repo)

    amu_binary_bytes = git_blob(amu_repo, AMU_COMMIT, AMU_BINARY_PATH)
    runner_source_bytes = git_blob(amu_repo, AMU_COMMIT, AMU_RUNNER_SOURCE)
    if sha(amu_binary_bytes) != AMU_BINARY_SHA256:
        raise RuntimeError("pinned Amu Linux compiler digest mismatch")
    if sha(runner_source_bytes) != AMU_RUNNER_SHA256:
        raise RuntimeError("pinned Amu KX64 runner source digest mismatch")
    if sha(git_blob(kotoba_repo, KOTOBA_COMMIT, KOTOBA_JCS_PATH)) != KOTOBA_JCS_SHA256:
        raise RuntimeError("pinned Kotoba JCS source digest mismatch")
    if sha(git_blob(kotoba_repo, KOTOBA_COMMIT, KOTOBA_STORE_IO_PATH)) != KOTOBA_STORE_IO_SHA256:
        raise RuntimeError("pinned Kotoba Hata store source digest mismatch")

    amu_binary = out / "amu-linux-x86_64"
    write(amu_binary, amu_binary_bytes)
    amu_binary.chmod(0o700)
    calls = []
    compile_env = {"PATH": "/nonexistent", "KEXE_CAP_RESOURCES_35": str(out),
                   "KEXE_STACK_BYTES": "8388608"}
    candidate_compiler, generations, candidate_sources_sha = derive_project_compiler(
        amu_binary, amu_repo, out, compile_env, calls)
    runner_source = out / "x86_64-kx64-runner.kotoba"
    write(runner_source, runner_source_bytes)
    cli, lock, source_digests = locked_project(out, kotoba_repo)

    artifact = out / "cron-store.kx64"
    run("compile-project", [candidate_compiler, "compile", cli, "--target", "x86_64-linux",
        "--output", artifact, "--format", "kx64-v1", "--source-lock", lock,
        "--source-lock-sha256", sha(lock.read_bytes())], out, compile_env, calls)
    head, separator, payload_bytes = artifact.read_bytes().partition(b"\n\n")
    match = re.fullmatch(rb"KX64V1 x86_64-linux sysv-ctx-v11 ([0-9]+) 0", head)
    if not separator or not match or len(payload_bytes) != int(match.group(1)):
        raise RuntimeError("Amu emitted an invalid KX64V1 artifact")
    payload = out / "cron-store.payload"
    write(payload, payload_bytes)

    runner = out / "kx64-runner.elf"
    run("compile-runner", [candidate_compiler, "compile", runner_source, "--target", "x86_64-linux",
        "--output", runner, "--format", "kx64-runner"], out, compile_env, calls)
    if sha(runner.read_bytes()) != AMU_CANDIDATE_RUNNER_SHA256:
        raise RuntimeError("derived Amu candidate KX64 runner digest mismatch")
    runner.chmod(0o700)

    pause_scope = out / "pause-marker-scope"
    (pause_scope / "d").mkdir(parents=True)
    pause_stamp = dt.datetime.now().astimezone().isoformat(timespec="seconds")
    pause_reason = "operator request"
    execute("runtime-global-pause-positive", runner, payload, pause_scope,
            "pause-global", pause_stamp, pause_reason, 0, out, calls)
    marker = pause_scope / "d/paused"
    expected_pause = f"{pause_stamp} {pause_reason}\n"
    if marker.read_text(encoding="utf-8") != expected_pause:
        raise RuntimeError(f"global pause marker mismatch: {marker.read_text(encoding='utf-8')!r}")
    status_stdout = execute("runtime-global-pause-status", runner, payload, pause_scope,
                            "status-global", "", "", 0, out, calls)
    if b"paused " not in status_stdout or b"operator request" not in status_stdout:
        raise RuntimeError(f"global pause status did not read the marker: {status_stdout!r}")

    execute("runtime-global-pause-invalid-time", runner, payload, pause_scope,
            "pause-global", "not-an-iso-time", pause_reason, 2, out, calls,
            allow_stderr=True)
    if marker.read_text(encoding="utf-8") != expected_pause:
        raise RuntimeError("invalid global pause timestamp changed the existing marker")

    resume_stdout = execute("runtime-global-resume-positive", runner, payload, pause_scope,
                            "resume-global", "", "", 0, out, calls)
    if b"resumed" not in resume_stdout or marker.exists():
        raise RuntimeError(f"global resume did not remove the active marker: {resume_stdout!r}")
    resume_absent_stdout = execute("runtime-global-resume-absent", runner, payload, pause_scope,
                                   "resume-global", "", "", 0, out, calls)
    if b"nothing to resume" not in resume_absent_stdout or marker.exists():
        raise RuntimeError(f"second global resume did not leave the marker absent: {resume_absent_stdout!r}")

    source_revision = subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD"]).decode().strip()
    package = out / "package"
    package_bin = package / "bin"
    package_bin.mkdir(parents=True)
    package_launcher = package_bin / "itonami-agent"
    package_runner = package_bin / "cron-jobs-runner"
    package_payload = package_bin / "cron-jobs.payload"
    shutil.copy2(ROOT / "bin/itonami-agent", package_launcher)
    shutil.copy2(runner, package_runner)
    shutil.copy2(payload, package_payload)
    package_launcher.chmod(0o700)
    package_runner.chmod(0o700)
    package_manifest = {
        "format": "itonami.cron-store-linux-native-candidate-package.v1",
        "candidate_only": True,
        "target": "x86_64-linux",
        "itonami_source_revision": source_revision,
        "amu_source_commit": AMU_COMMIT,
        "amu_candidate_compiler_sha256": sha(candidate_compiler.read_bytes()),
        "kotoba_source_commit": KOTOBA_COMMIT,
        "project_kx64_sha256": sha(artifact.read_bytes()),
        "project_payload_sha256": sha(payload_bytes),
        "runner_elf_sha256": sha(runner.read_bytes()),
        "launcher_sha256": sha(package_launcher.read_bytes()),
        "capabilities": ["cli/args", "clock/now", "entropy/draw", "fs/app-data", "io/write", "io/write-error"],
        "adoption": "not-public; Amu experimental source candidate",
    }
    manifest_path = package / "candidate-package.json"
    manifest_path.write_text(json.dumps(package_manifest, indent=2, sort_keys=True) + "\n",
                             encoding="utf-8")

    positive = out / "positive-scope"
    (positive / "d").mkdir(parents=True)
    (positive / "d/jobs.json").write_text(
        '{"jobs":[{"id":"remove-me","keep":1},{"id":"stay","future":1.25e+7}],'
        '"unknown":{"n":-0.0001},"updated_at":"old"}', encoding="ascii")
    positive_stdout = execute("runtime-clock-fs-positive", runner, payload, positive,
                              "remove", "remove-me", "", 0, out, calls)
    persisted = (positive / "d/jobs.json").read_text(encoding="ascii")
    prefix = ('{"jobs":[{"id":"stay","future":1.25e+7}],'
              '"unknown":{"n":-0.0001},"updated_at":"')
    if not persisted.startswith(prefix) or not persisted.endswith('"}'):
        raise RuntimeError(f"positive store output mismatch: {persisted!r}")
    timestamp = persisted[len(prefix):-2]
    parsed = dt.datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    if parsed.tzinfo is None or abs(parsed.timestamp() - time.time()) > 10:
        raise RuntimeError(f"Amu wall clock is outside 10 seconds of host UTC: {timestamp}")
    if (positive / "d/.jobs.json.tmp").exists():
        raise RuntimeError("positive store left a temporary file")

    refusal = out / "refusal-scope"
    (refusal / "d").mkdir(parents=True)
    malformed = '{"jobs":'
    (refusal / "d/jobs.json").write_text(malformed, encoding="ascii")
    refusal_stdout = execute("runtime-clock-fs-refusal", runner, payload, refusal,
                             "remove", "remove-me", "", 1, out, calls)
    if (refusal / "d/jobs.json").read_text(encoding="ascii") != malformed:
        raise RuntimeError("refusal modified malformed source JSON")
    if (refusal / "d/.jobs.json.tmp").exists():
        raise RuntimeError("refusal left a temporary file")

    launcher_positive = out / "launcher-positive-scope"
    (launcher_positive / "d").mkdir(parents=True)
    (launcher_positive / "d/jobs.json").write_text(
        '{"jobs":[{"id":"remove-me","keep":1},{"id":"stay","future":1.25e+7}],'
        '"unknown":{"n":-0.0001},"updated_at":"old"}', encoding="ascii")
    launcher_positive_stdout = execute_launcher("launcher-clock-fs-positive", package_launcher,
                                                launcher_positive, "remove", "remove-me", "", 0, out, calls)
    launcher_persisted = (launcher_positive / "d/jobs.json").read_text(encoding="ascii")
    if not launcher_persisted.startswith(prefix) or not launcher_persisted.endswith('"}'):
        raise RuntimeError(f"launcher positive store output mismatch: {launcher_persisted!r}")
    launcher_timestamp = launcher_persisted[len(prefix):-2]
    parsed = dt.datetime.fromisoformat(launcher_timestamp.replace("Z", "+00:00"))
    if parsed.tzinfo is None or abs(parsed.timestamp() - time.time()) > 10:
        raise RuntimeError(f"launcher timestamp is outside 10 seconds of host UTC: {launcher_timestamp}")
    if (launcher_positive / "d/.jobs.json.tmp").exists():
        raise RuntimeError("launcher positive store left a temporary file")

    launcher_refusal = out / "launcher-refusal-scope"
    (launcher_refusal / "d").mkdir(parents=True)
    (launcher_refusal / "d/jobs.json").write_text(malformed, encoding="ascii")
    execute_launcher("launcher-clock-fs-refusal", package_launcher, launcher_refusal,
                     "remove", "remove-me", "", 1, out, calls)
    if (launcher_refusal / "d/jobs.json").read_text(encoding="ascii") != malformed:
        raise RuntimeError("launcher refusal modified malformed source JSON")
    if (launcher_refusal / "d/.jobs.json.tmp").exists():
        raise RuntimeError("launcher refusal left a temporary file")

    missing_package_bin = out / "missing-package/bin"
    missing_package_bin.mkdir(parents=True)
    missing_launcher = missing_package_bin / "itonami-agent"
    shutil.copy2(ROOT / "bin/itonami-agent", missing_launcher)
    missing_scope = out / "launcher-missing-scope"
    (missing_scope / "d").mkdir(parents=True)
    missing_env = dict(os.environ)
    missing_env.pop("ITONAMI_CRON_JOBS_RUNNER", None)
    missing_env.pop("ITONAMI_CRON_JOBS_PAYLOAD", None)
    missing_result = subprocess.run([str(missing_launcher), "cron", "jobs", "remove",
        str(missing_scope / "d"), "remove-me"], cwd=ROOT, env=missing_env,
        capture_output=True, timeout=120)
    calls.append({"name": "launcher-missing-artifact", "exit": missing_result.returncode,
                  "seconds": 0, "stdout_sha256": sha(missing_result.stdout),
                  "stderr_sha256": sha(missing_result.stderr)})
    write(out / "launcher-missing-artifact.stdout", missing_result.stdout)
    write(out / "launcher-missing-artifact.stderr", missing_result.stderr)
    if missing_result.returncode != 78 or b"native artifact missing" not in missing_result.stderr:
        raise RuntimeError(f"launcher missing-artifact refusal mismatch: "
                           f"exit={missing_result.returncode} stderr={missing_result.stderr!r}")

    launcher_global_pause = out / "launcher-global-pause-scope"
    (launcher_global_pause / "d").mkdir(parents=True)
    launcher_global_reason = "operator request"
    launcher_global_pause_stdout = execute_launcher(
        "launcher-global-pause-positive", package_launcher, launcher_global_pause,
        "pause-global", launcher_global_reason, "", 0, out, calls)
    launcher_global_marker = launcher_global_pause / "itonami/paused"
    launcher_global_contents = launcher_global_marker.read_text(encoding="utf-8")
    launcher_global_timestamp, _, launcher_global_saved_reason = launcher_global_contents.rstrip("\n").partition(" ")
    parsed_global_timestamp = dt.datetime.fromisoformat(launcher_global_timestamp)
    if (launcher_global_saved_reason != launcher_global_reason
            or abs(parsed_global_timestamp.timestamp() - time.time()) > 10
            or b"paused" not in launcher_global_pause_stdout):
        raise RuntimeError(f"launcher global pause marker/output mismatch: "
                           f"{launcher_global_contents!r} {launcher_global_pause_stdout!r}")

    launcher_global_status_stdout = execute_launcher(
        "launcher-global-status-positive", package_launcher, launcher_global_pause,
        "status-global", "", "", 0, out, calls)
    if (b"paused " not in launcher_global_status_stdout
            or launcher_global_reason.encode() not in launcher_global_status_stdout):
        raise RuntimeError(f"launcher global status did not read marker: {launcher_global_status_stdout!r}")

    launcher_global_resume_stdout = execute_launcher(
        "launcher-global-resume-positive", package_launcher, launcher_global_pause,
        "resume-global", "", "", 0, out, calls)
    if b"resumed" not in launcher_global_resume_stdout or launcher_global_marker.exists():
        raise RuntimeError(f"launcher global resume did not remove marker: {launcher_global_resume_stdout!r}")

    launcher_global_absent_stdout = execute_launcher(
        "launcher-global-resume-absent", package_launcher, launcher_global_pause,
        "resume-global", "", "", 0, out, calls)
    if b"nothing to resume" not in launcher_global_absent_stdout or launcher_global_marker.exists():
        raise RuntimeError(f"second launcher global resume did not leave the marker absent: {launcher_global_absent_stdout!r}")

    list_scope = out / "list-scope"
    (list_scope / "d").mkdir(parents=True)
    jobs_document = ('{"jobs":[{"id":"active","name":"A","prompt":"p",'
                     '"enabled":true,"private":"omit"},{"id":"paused",'
                     '"enabled":false,"state":"paused"}],"extension":1.25e+7}')
    (list_scope / "d/jobs.json").write_text(jobs_document, encoding="ascii")
    list_stdout = execute("runtime-list-active-only", runner, payload, list_scope,
                          "list", "false", "", 0, out, calls)
    expected_list = b'{"jobs":[{"id":"active","name":"A","prompt":"p","enabled":true}]}'
    if expected_list not in list_stdout or b'"private"' in list_stdout or b'"paused"' in list_stdout:
        raise RuntimeError(f"native list projection/filter mismatch: {list_stdout!r}")
    if (list_scope / "d/jobs.json").read_text(encoding="ascii") != jobs_document:
        raise RuntimeError("read-only jobs list modified jobs.json")

    pause_scope = out / "pause-scope"
    (pause_scope / "d").mkdir(parents=True)
    pause_document = ('{"jobs":[{"id":"pause-me","enabled":true,"state":"scheduled",'
                      '"paused_at":null,"future":1.25e+7},{"id":"stay","future":-0.0001}],'
                      '"extension":{"x":true},"updated_at":"old"}')
    (pause_scope / "d/jobs.json").write_text(pause_document, encoding="ascii")
    pause_stdout = execute("runtime-pause-positive", runner, payload, pause_scope,
                           "pause", "pause-me", "operator request", 0, out, calls)
    paused_document = (pause_scope / "d/jobs.json").read_text(encoding="ascii")
    if ('"id":"pause-me","enabled":false,"state":"paused","paused_at":"' not in paused_document
            or '"paused_reason":"operator request"' not in paused_document
            or '"future":1.25e+7' not in paused_document
            or '"id":"stay","future":-0.0001' not in paused_document
            or '"extension":{"x":true}' not in paused_document):
        raise RuntimeError(f"pause output did not preserve/update expected fields: {paused_document!r}")
    pause_at = re.search(r'"paused_at":"([^"]+)"', paused_document)
    pause_updated = re.search(r'"updated_at":"([^"]+)"', paused_document)
    if not pause_at or not pause_updated or pause_at.group(1) != pause_updated.group(1):
        raise RuntimeError(f"pause metadata timestamps do not match: {paused_document!r}")
    parsed = dt.datetime.fromisoformat(pause_at.group(1).replace("Z", "+00:00"))
    if parsed.tzinfo is None or abs(parsed.timestamp() - time.time()) > 10:
        raise RuntimeError(f"pause timestamp is outside 10 seconds of host UTC: {pause_at.group(1)}")
    if (pause_scope / "d/.jobs.json.tmp").exists():
        raise RuntimeError("pause positive store left a temporary file")

    pause_refusal = out / "pause-refusal-scope"
    (pause_refusal / "d").mkdir(parents=True)
    pause_refusal_document = '{"jobs":[{"id":"present","enabled":true}],"extension":7}'
    (pause_refusal / "d/jobs.json").write_text(pause_refusal_document, encoding="ascii")
    execute("runtime-pause-missing-refusal", runner, payload, pause_refusal,
            "pause", "missing", "", 2, out, calls, allow_stderr=True)
    if (pause_refusal / "d/jobs.json").read_text(encoding="ascii") != pause_refusal_document:
        raise RuntimeError("pause missing-id refusal modified jobs.json")
    if (pause_refusal / "d/.jobs.json.tmp").exists():
        raise RuntimeError("pause refusal left a temporary file")

    launcher_pause = out / "launcher-pause-scope"
    (launcher_pause / "d").mkdir(parents=True)
    (launcher_pause / "d/jobs.json").write_text(pause_document, encoding="ascii")
    launcher_pause_stdout = execute_launcher("launcher-pause-positive", package_launcher,
                                             launcher_pause, "pause", "pause-me",
                                             "operator request", 0, out, calls)
    launcher_paused = (launcher_pause / "d/jobs.json").read_text(encoding="ascii")
    if ('"enabled":false,"state":"paused"' not in launcher_paused
            or '"paused_reason":"operator request"' not in launcher_paused
            or '"extension":{"x":true}' not in launcher_paused):
        raise RuntimeError(f"launcher pause output mismatch: {launcher_paused!r}")
    if (launcher_pause / "d/.jobs.json.tmp").exists():
        raise RuntimeError("launcher pause left a temporary file")

    launcher_pause_refusal = out / "launcher-pause-refusal-scope"
    (launcher_pause_refusal / "d").mkdir(parents=True)
    (launcher_pause_refusal / "d/jobs.json").write_text(pause_refusal_document, encoding="ascii")
    execute_launcher("launcher-pause-missing-refusal", package_launcher,
                     launcher_pause_refusal, "pause", "missing", "", 2, out, calls)
    if (launcher_pause_refusal / "d/jobs.json").read_text(encoding="ascii") != pause_refusal_document:
        raise RuntimeError("launcher pause refusal modified jobs.json")

    resume_document = ('{"jobs":[{"id":"resume-me","enabled":false,"state":"paused",'
                       '"paused_at":"old","paused_reason":"old",'
                       '"schedule":{"kind":"cron","expr":"*/15 * * * *"},'
                       '"next_run_at":null,"future":1.25e+7}],"extension":{"x":true}}')
    resume_scope = out / "resume-scope"
    (resume_scope / "d").mkdir(parents=True)
    (resume_scope / "d/jobs.json").write_text(resume_document, encoding="ascii")
    resume_stdout = execute("runtime-resume-cron-positive", runner, payload, resume_scope,
                            "resume", "resume-me", "+0000", 0, out, calls)
    resumed = json.loads((resume_scope / "d/jobs.json").read_text(encoding="ascii"))
    resumed_job = resumed["jobs"][0]
    if (resumed_job.get("enabled") is not True or resumed_job.get("state") != "scheduled"
            or resumed_job.get("paused_at") is not None
            or resumed_job.get("paused_reason") is not None
            or resumed.get("extension") != {"x": True}
            or resumed_job.get("future") != 1.25e7):
        raise RuntimeError(f"resume did not restore job state or preserve extensions: {resumed!r}")
    next_at = dt.datetime.fromisoformat(resumed_job["next_run_at"].replace("Z", "+00:00"))
    now = dt.datetime.now(dt.timezone.utc)
    if (next_at <= now or (next_at - now).total_seconds() > 15 * 60
            or next_at.minute % 15 != 0 or next_at.second != 0):
        raise RuntimeError(f"resume cron next_run_at is outside expected UTC quarter hour: {next_at}")
    updated_at = dt.datetime.fromisoformat(resumed["updated_at"].replace("Z", "+00:00"))
    if abs(updated_at.timestamp() - time.time()) > 10:
        raise RuntimeError(f"resume updated_at is outside 10 seconds of host UTC: {updated_at}")
    if (resume_scope / "d/.jobs.json.tmp").exists():
        raise RuntimeError("resume positive store left a temporary file")

    expired_once_scope = out / "resume-expired-once-scope"
    (expired_once_scope / "d").mkdir(parents=True)
    (expired_once_scope / "d/jobs.json").write_text(
        '{"jobs":[{"id":"expired","enabled":false,"schedule":{"kind":"once",'
        '"run_at":"2020-01-01T00:00:00Z"},"next_run_at":null}]}', encoding="ascii")
    execute("runtime-resume-expired-once", runner, payload, expired_once_scope,
            "resume", "expired", "+0000", 0, out, calls)
    expired = json.loads((expired_once_scope / "d/jobs.json").read_text(encoding="ascii"))["jobs"][0]
    if expired.get("enabled") is not True or expired.get("state") != "completed" or expired.get("next_run_at") is not None:
        raise RuntimeError(f"expired one-shot resume mismatch: {expired!r}")

    interval_scope = out / "resume-interval-scope"
    (interval_scope / "d").mkdir(parents=True)
    (interval_scope / "d/jobs.json").write_text(
        '{"jobs":[{"id":"interval","enabled":false,"schedule":{"kind":"interval",'
        '"minutes":5},"next_run_at":null}]}', encoding="ascii")
    execute("runtime-resume-interval", runner, payload, interval_scope,
            "resume", "interval", "+0000", 0, out, calls)
    interval_result = json.loads((interval_scope / "d/jobs.json").read_text(encoding="ascii"))
    interval_job = interval_result["jobs"][0]
    interval_next = dt.datetime.fromisoformat(interval_job["next_run_at"].replace("Z", "+00:00"))
    interval_updated = dt.datetime.fromisoformat(interval_result["updated_at"].replace("Z", "+00:00"))
    if (interval_job.get("enabled") is not True or interval_job.get("state") != "scheduled"
            or (interval_next - interval_updated).total_seconds() != 5 * 60):
        raise RuntimeError(f"interval resume did not schedule exactly five minutes after now: {interval_result!r}")

    future_once_scope = out / "resume-future-once-scope"
    (future_once_scope / "d").mkdir(parents=True)
    (future_once_scope / "d/jobs.json").write_text(
        '{"jobs":[{"id":"future-once","enabled":false,"schedule":{"kind":"once",'
        '"run_at":"2099-01-01T09:00:00+09:00"},"next_run_at":null}]}', encoding="ascii")
    execute("runtime-resume-future-once", runner, payload, future_once_scope,
            "resume", "future-once", "+0000", 0, out, calls)
    future_once = json.loads((future_once_scope / "d/jobs.json").read_text(encoding="ascii"))["jobs"][0]
    future_run_at = dt.datetime.fromisoformat(future_once["schedule"]["run_at"].replace("Z", "+00:00"))
    future_next_at = dt.datetime.fromisoformat(future_once["next_run_at"].replace("Z", "+00:00"))
    if future_once.get("state") != "scheduled" or future_next_at != future_run_at:
        raise RuntimeError(f"future one-shot resume did not preserve its instant: {future_once!r}")

    invalid_resume_scope = out / "resume-invalid-scope"
    (invalid_resume_scope / "d").mkdir(parents=True)
    invalid_resume_document = '{"jobs":[{"id":"bad","schedule":{"kind":"cron","expr":"* * *"}}]}'
    (invalid_resume_scope / "d/jobs.json").write_text(invalid_resume_document, encoding="ascii")
    execute("runtime-resume-invalid-refusal", runner, payload, invalid_resume_scope,
            "resume", "bad", "+0000", 2, out, calls, allow_stderr=True)
    if (invalid_resume_scope / "d/jobs.json").read_text(encoding="ascii") != invalid_resume_document:
        raise RuntimeError("invalid resume refusal modified jobs.json")

    create_scope = out / "create-scope"
    (create_scope / "d").mkdir(parents=True)
    create_document = '{"jobs":[],"extension":{"keep":1.25e+7}}'
    (create_scope / "d/jobs.json").write_text(create_document, encoding="ascii")
    create_stdout = execute("runtime-create-positive", runner, payload, create_scope,
                            "create", "every 5m", "native prompt", 0, out, calls,
                            extra1="Native prompt job", extra2="+0000")
    created_document = json.loads((create_scope / "d/jobs.json").read_text(encoding="ascii"))
    if len(created_document.get("jobs", [])) != 1:
        raise RuntimeError(f"create did not append exactly one cron job: {created_document!r}")
    created_job = created_document["jobs"][0]
    if (not re.fullmatch(r"[0-9a-f]{12}", created_job.get("id", ""))
            or created_job.get("name") != "Native prompt job"
            or created_job.get("prompt") != "native prompt"
            or created_job.get("schedule", {}).get("kind") != "interval"
            or created_job.get("schedule", {}).get("minutes") != 5
            or created_job.get("enabled") is not True
            or created_document.get("extension") != {"keep": 1.25e7}):
        raise RuntimeError(f"created job fields or extension preservation mismatch: {created_document!r}")
    create_updated = dt.datetime.fromisoformat(created_document["updated_at"].replace("Z", "+00:00"))
    create_next = dt.datetime.fromisoformat(created_job["next_run_at"].replace("Z", "+00:00"))
    if (abs(create_updated.timestamp() - time.time()) > 10
            or (create_next - create_updated).total_seconds() != 5 * 60):
        raise RuntimeError(f"create clock or next-run mismatch: {created_document!r}")
    if (create_scope / "d/.jobs.json.tmp").exists():
        raise RuntimeError("create positive store left a temporary file")

    create_refusal = out / "create-refusal-scope"
    (create_refusal / "d").mkdir(parents=True)
    create_refusal_document = '{"jobs":[],"extension":true}'
    (create_refusal / "d/jobs.json").write_text(create_refusal_document, encoding="ascii")
    execute("runtime-create-invalid-schedule-refusal", runner, payload, create_refusal,
            "create", "not-a-schedule", "native prompt", 2, out, calls,
            allow_stderr=True, extra1="", extra2="+0000")
    if (create_refusal / "d/jobs.json").read_text(encoding="ascii") != create_refusal_document:
        raise RuntimeError("invalid create refusal modified jobs.json")
    if (create_refusal / "d/.jobs.json.tmp").exists():
        raise RuntimeError("create refusal left a temporary file")

    create_prompt_refusal = out / "create-prompt-refusal-scope"
    (create_prompt_refusal / "d").mkdir(parents=True)
    (create_prompt_refusal / "d/jobs.json").write_text(create_refusal_document, encoding="ascii")
    execute("runtime-create-empty-prompt-refusal", runner, payload, create_prompt_refusal,
            "create", "every 5m", "", 2, out, calls,
            allow_stderr=True, extra1="", extra2="+0000")
    if (create_prompt_refusal / "d/jobs.json").read_text(encoding="ascii") != create_refusal_document:
        raise RuntimeError("empty-prompt create refusal modified jobs.json")

    update_schedule_document = (
        '{"jobs":[{"id":"change-me","schedule":{"kind":"interval","minutes":5},'
        '"schedule_display":"every 5m","next_run_at":null,"future":1.25e+7},'
        '{"id":"stay","future":-0.0001}],"extension":{"keep":true},"updated_at":"old"}')
    update_scope = out / "update-scope"
    (update_scope / "d").mkdir(parents=True)
    update_document = (
        '{"jobs":[{"id":"update-me","name":"old","prompt":"before",'
        '"continuity":true,"skills":["old"],"skill":"old",'
        '"repeat":{"times":1,"completed":2},'
        '"schedule":{"kind":"interval","minutes":5},"next_run_at":null,'
        '"future":1.25e+7}],"extension":{"keep":true}}')
    update_patch = (
        '{"prompt":"","name":"new","continuity":false,"context_from":[],'
        '"skills":[],"repeat":2,"schedule":"every 10m"}')
    (update_scope / "d/jobs.json").write_text(update_document, encoding="ascii")
    execute("runtime-update-positive", runner, payload, update_scope,
            "update", "update-me", update_patch, 0, out, calls, extra1="+0000")
    updated_doc = json.loads((update_scope / "d/jobs.json").read_text(encoding="ascii"))
    updated_job = updated_doc["jobs"][0]
    updated_at = dt.datetime.fromisoformat(updated_doc["updated_at"].replace("Z", "+00:00"))
    updated_next = dt.datetime.fromisoformat(updated_job["next_run_at"].replace("Z", "+00:00"))
    if (updated_job.get("prompt") != "" or updated_job.get("name") != "new"
            or updated_job.get("continuity") is not False
            or updated_job.get("context_from") != [] or updated_job.get("skills") != []
            or updated_job.get("skill") is not None
            or updated_job.get("repeat") != {"times": 2, "completed": 2}
            or updated_job.get("schedule") != {"kind": "interval", "minutes": 10,
                                                "display": "every 10m"}
            or updated_job.get("future") != 1.25e7
            or updated_doc.get("extension") != {"keep": True}
            or (updated_next - updated_at).total_seconds() != 10 * 60
            or abs(updated_at.timestamp() - time.time()) > 10):
        raise RuntimeError(f"update fields, timing or extension mismatch: {updated_doc!r}")
    if (update_scope / "d/.jobs.json.tmp").exists():
        raise RuntimeError("update positive left a temporary file")

    for label, target, patch_text in (("unknown", "update-me", '{"unexpected":1}'),
                                      ("invalid-schedule", "update-me", '{"schedule":"not-a-schedule"}'),
                                      ("missing", "missing", '{"prompt":"changed"}')):
        refusal_scope = out / f"update-{label}-scope"
        (refusal_scope / "d").mkdir(parents=True)
        (refusal_scope / "d/jobs.json").write_text(update_document, encoding="ascii")
        execute(f"runtime-update-{label}-refusal", runner, payload, refusal_scope,
                "update", target, patch_text, 2, out, calls,
                allow_stderr=True, extra1="+0000")
        if (refusal_scope / "d/jobs.json").read_text(encoding="ascii") != update_document:
            raise RuntimeError(f"update {label} refusal modified jobs.json")
        if (refusal_scope / "d/.jobs.json.tmp").exists():
            raise RuntimeError(f"update {label} refusal left a temporary file")

    launcher_create_scope = out / "launcher-create-scope"
    (launcher_create_scope / "d").mkdir(parents=True)
    (launcher_create_scope / "d/jobs.json").write_text(create_document, encoding="ascii")
    launcher_create_stdout = execute_launcher(
        "launcher-create-positive", package_launcher, launcher_create_scope,
        "create", "every 5m", "native prompt", 0, out, calls,
        env_overrides={"TZ": "UTC"}, extra1="Launcher prompt job")
    launcher_created_doc = json.loads((launcher_create_scope / "d/jobs.json").read_text(encoding="ascii"))
    if len(launcher_created_doc.get("jobs", [])) != 1:
        raise RuntimeError(f"launcher create did not append exactly one job: {launcher_created_doc!r}")
    launcher_created_job = launcher_created_doc["jobs"][0]
    if (not re.fullmatch(r"[0-9a-f]{12}", launcher_created_job.get("id", ""))
            or launcher_created_job.get("name") != "Launcher prompt job"
            or launcher_created_job.get("prompt") != "native prompt"
            or launcher_created_job.get("schedule", {}).get("kind") != "interval"
            or launcher_created_job.get("schedule", {}).get("minutes") != 5
            or launcher_created_doc.get("extension") != {"keep": 1.25e7}):
        raise RuntimeError(f"launcher create fields or extension preservation mismatch: {launcher_created_doc!r}")
    launcher_create_updated = dt.datetime.fromisoformat(
        launcher_created_doc["updated_at"].replace("Z", "+00:00"))
    launcher_create_next = dt.datetime.fromisoformat(
        launcher_created_job["next_run_at"].replace("Z", "+00:00"))
    if (abs(launcher_create_updated.timestamp() - time.time()) > 10
            or (launcher_create_next - launcher_create_updated).total_seconds() != 5 * 60):
        raise RuntimeError(f"launcher create timestamp or next-run mismatch: {launcher_created_doc!r}")
    if (launcher_create_scope / "d/.jobs.json.tmp").exists():
        raise RuntimeError("launcher create positive store left a temporary file")

    launcher_create_refusal = out / "launcher-create-refusal-scope"
    (launcher_create_refusal / "d").mkdir(parents=True)
    (launcher_create_refusal / "d/jobs.json").write_text(create_refusal_document, encoding="ascii")
    execute_launcher("launcher-create-invalid-schedule-refusal", package_launcher,
                     launcher_create_refusal, "create", "not-a-schedule", "native prompt", 2,
                     out, calls, env_overrides={"TZ": "UTC"})
    if (launcher_create_refusal / "d/jobs.json").read_text(encoding="ascii") != create_refusal_document:
        raise RuntimeError("launcher invalid-create refusal modified jobs.json")
    if (launcher_create_refusal / "d/.jobs.json.tmp").exists():
        raise RuntimeError("launcher create refusal left a temporary file")

    launcher_update_full_scope = out / "launcher-update-full-scope"
    (launcher_update_full_scope / "d").mkdir(parents=True)
    (launcher_update_full_scope / "d/jobs.json").write_text(update_document, encoding="ascii")
    execute_launcher("launcher-update-positive", package_launcher, launcher_update_full_scope,
                     "update", "update-me", update_patch, 0, out, calls,
                     env_overrides={"TZ": "UTC"})
    launcher_updated_doc = json.loads(
        (launcher_update_full_scope / "d/jobs.json").read_text(encoding="ascii"))
    launcher_updated_job = launcher_updated_doc["jobs"][0]
    if (launcher_updated_job.get("prompt") != ""
            or launcher_updated_job.get("name") != "new"
            or launcher_updated_job.get("continuity") is not False
            or launcher_updated_job.get("context_from") != []
            or launcher_updated_job.get("skills") != []
            or launcher_updated_job.get("skill") is not None
            or launcher_updated_job.get("repeat") != {"times": 2, "completed": 2}
            or launcher_updated_job.get("schedule", {}).get("minutes") != 10
            or launcher_updated_doc.get("extension") != {"keep": True}):
        raise RuntimeError(f"launcher update fields mismatch: {launcher_updated_doc!r}")

    launcher_update_unknown = out / "launcher-update-unknown-scope"
    (launcher_update_unknown / "d").mkdir(parents=True)
    (launcher_update_unknown / "d/jobs.json").write_text(update_document, encoding="ascii")
    execute_launcher("launcher-update-unknown-refusal", package_launcher, launcher_update_unknown,
                     "update", "update-me", '{"unexpected":1}', 2, out, calls,
                     env_overrides={"TZ": "UTC"})
    if ((launcher_update_unknown / "d/jobs.json").read_text(encoding="ascii") != update_document
            or (launcher_update_unknown / "d/.jobs.json.tmp").exists()):
        raise RuntimeError("launcher unknown-update refusal modified the document or left a temp")

    launcher_update_invalid_schedule = out / "launcher-update-invalid-schedule-scope"
    (launcher_update_invalid_schedule / "d").mkdir(parents=True)
    (launcher_update_invalid_schedule / "d/jobs.json").write_text(update_document, encoding="ascii")
    execute_launcher("launcher-update-invalid-schedule-refusal", package_launcher,
                     launcher_update_invalid_schedule, "update", "update-me",
                     '{"schedule":"not-a-schedule"}', 2, out, calls,
                     env_overrides={"TZ": "UTC"})
    if ((launcher_update_invalid_schedule / "d/jobs.json").read_text(encoding="ascii")
            != update_document
            or (launcher_update_invalid_schedule / "d/.jobs.json.tmp").exists()):
        raise RuntimeError("launcher invalid-schedule update refusal modified the document or left a temp")

    launcher_create_prompt_refusal = out / "launcher-create-prompt-refusal-scope"
    (launcher_create_prompt_refusal / "d").mkdir(parents=True)
    (launcher_create_prompt_refusal / "d/jobs.json").write_text(create_refusal_document, encoding="ascii")
    execute_launcher("launcher-create-empty-prompt-refusal", package_launcher,
                     launcher_create_prompt_refusal, "create", "every 5m", "", 2,
                     out, calls, env_overrides={"TZ": "UTC"}, append_empty_option=True)
    if ((launcher_create_prompt_refusal / "d/jobs.json").read_text(encoding="ascii")
            != create_refusal_document):
        raise RuntimeError("launcher empty-prompt create refusal modified jobs.json")
    if (launcher_create_prompt_refusal / "d/.jobs.json.tmp").exists():
        raise RuntimeError("launcher create prompt refusal left a temporary file")

    launcher_resume = out / "launcher-resume-scope"
    (launcher_resume / "d").mkdir(parents=True)
    (launcher_resume / "d/jobs.json").write_text(resume_document, encoding="ascii")
    launcher_resume_stdout = execute_launcher("launcher-resume-cron-positive", package_launcher,
                                              launcher_resume, "resume", "resume-me", "", 0,
                                              out, calls, env_overrides={"TZ": "UTC"})
    launcher_resumed = json.loads((launcher_resume / "d/jobs.json").read_text(encoding="ascii"))
    launcher_next = dt.datetime.fromisoformat(
        launcher_resumed["jobs"][0]["next_run_at"].replace("Z", "+00:00"))
    if (launcher_resumed["jobs"][0].get("state") != "scheduled"
            or launcher_resumed["jobs"][0].get("enabled") is not True
            or launcher_next <= dt.datetime.now(dt.timezone.utc)
            or launcher_next.minute % 15 != 0 or launcher_next.second != 0):
        raise RuntimeError(f"launcher resume cron output mismatch: {launcher_resumed!r}")

    launcher_invalid_resume = out / "launcher-resume-invalid-scope"
    (launcher_invalid_resume / "d").mkdir(parents=True)
    (launcher_invalid_resume / "d/jobs.json").write_text(invalid_resume_document, encoding="ascii")
    execute_launcher("launcher-resume-invalid-refusal", package_launcher,
                     launcher_invalid_resume, "resume", "bad", "", 2, out, calls,
                     env_overrides={"TZ": "UTC"})
    if (launcher_invalid_resume / "d/jobs.json").read_text(encoding="ascii") != invalid_resume_document:
        raise RuntimeError("launcher invalid-resume refusal modified jobs.json")

    launcher_list = out / "launcher-list-scope"
    (launcher_list / "d").mkdir(parents=True)
    (launcher_list / "d/jobs.json").write_text(jobs_document, encoding="ascii")
    launcher_list_stdout = execute_launcher("launcher-list-active-only", package_launcher,
                                            launcher_list, "list", "false", "", 0, out, calls)
    if expected_list not in launcher_list_stdout or b'"private"' in launcher_list_stdout or b'"paused"' in launcher_list_stdout:
        raise RuntimeError(f"launcher list projection/filter mismatch: {launcher_list_stdout!r}")
    if (launcher_list / "d/jobs.json").read_text(encoding="ascii") != jobs_document:
        raise RuntimeError("launcher jobs list modified jobs.json")

    list_refusal = out / "list-refusal-scope"
    (list_refusal / "d").mkdir(parents=True)
    malformed_list = '{"jobs":[false]}'
    (list_refusal / "d/jobs.json").write_text(malformed_list, encoding="ascii")
    execute_launcher("launcher-list-refusal", package_launcher, list_refusal,
                     "list", "", "", 2, out, calls)
    if (list_refusal / "d/jobs.json").read_text(encoding="ascii") != malformed_list:
        raise RuntimeError("list refusal modified invalid jobs document")

    receipt = {
        "format": "itonami.cron-jobs-linux-native-gate.v1",
        "itonami_source_revision": source_revision,
        "amu_source_commit": AMU_COMMIT,
        "amu_linux_compiler_sha256": sha(amu_binary_bytes),
        "amu_candidate_source_sha256": candidate_sources_sha,
        "amu_candidate_compiler_sha256": sha(candidate_compiler.read_bytes()),
        "amu_candidate_generations": generations,
        "kotoba_source_commit": KOTOBA_COMMIT,
        "kotoba_jcs_source_sha256": KOTOBA_JCS_SHA256,
        "kotoba_store_io_source_sha256": KOTOBA_STORE_IO_SHA256,
        "runtime": "Amu x86_64-linux KX64V1 static runner",
        "project_source_lock_sha256": sha(lock.read_bytes()),
        "project_kx64_sha256": sha(artifact.read_bytes()),
        "project_payload_sha256": sha(payload_bytes),
        "runner_source_sha256": sha(runner_source_bytes),
        "runner_elf_sha256": sha(runner.read_bytes()),
        "sources_sha256": source_digests,
        "wall_timestamp": timestamp,
        "positive_runtime": "PASS",
        "refusal_runtime": "PASS",
        "launcher_positive_runtime": "PASS",
        "launcher_refusal_runtime": "PASS",
        "launcher_missing_artifact_refusal": "PASS",
        "list_active_only_runtime": "PASS",
        "list_active_only_launcher": "PASS",
        "list_invalid_job_refusal": "PASS",
        "pause_runtime": "PASS",
        "global_pause_runtime": "PASS",
        "global_pause_invalid_timestamp_refusal": "PASS",
        "global_pause_status_runtime": "PASS",
        "global_resume_positive_runtime": "PASS",
        "global_resume_idempotent_runtime": "PASS",
        "global_pause_launcher_runtime": "PASS",
        "global_status_launcher_runtime": "PASS",
        "global_resume_launcher_runtime": "PASS",
        "global_resume_idempotent_launcher": "PASS",
        "pause_missing_id_refusal_runtime": "PASS",
        "pause_launcher_runtime": "PASS",
        "pause_missing_id_refusal_launcher": "PASS",
        "resume_cron_runtime": "PASS",
        "resume_interval_runtime": "PASS",
        "resume_expired_once_runtime": "PASS",
        "resume_future_once_runtime": "PASS",
        "resume_invalid_schedule_refusal_runtime": "PASS",
        "resume_cron_launcher_runtime": "PASS",
        "resume_invalid_schedule_refusal_launcher": "PASS",
        "create_runtime": "PASS",
        "create_invalid_schedule_refusal": "PASS",
        "create_empty_prompt_refusal": "PASS",
        "create_launcher_runtime": "PASS",
        "create_invalid_schedule_refusal_launcher": "PASS",
        "create_empty_prompt_refusal_launcher": "PASS",
        "update_runtime": "PASS",
        "update_unknown_field_refusal": "PASS",
        "update_invalid_schedule_refusal": "PASS",
        "update_missing_target_refusal": "PASS",
        "update_launcher_runtime": "PASS",
        "update_launcher_unknown_field_refusal": "PASS",
        "update_launcher_invalid_schedule_refusal": "PASS",
        "candidate_package": {
            "manifest": "package/candidate-package.json",
            "manifest_sha256": sha(manifest_path.read_bytes()),
            "launcher_sha256": sha(package_launcher.read_bytes()),
            "runner_sha256": sha(package_runner.read_bytes()),
            "payload_sha256": sha(package_payload.read_bytes()),
        },
        "codesign": "not-applicable: Linux static ELF",
        "host_oracle_clock_check": "PASS within 10 seconds",
        "processes": calls,
        "stdout_sha256": {"positive": sha(positive_stdout), "refusal": sha(refusal_stdout),
                          "launcher_positive": sha(launcher_positive_stdout),
                          "pause": sha(pause_stdout), "launcher_pause": sha(launcher_pause_stdout),
                          "resume": sha(resume_stdout), "launcher_resume": sha(launcher_resume_stdout),
                          "launcher_create": sha(launcher_create_stdout)},
        "scope": "standalone Linux x86_64 native cron jobs and global pause-marker Kotoba CLI candidate with scoped FS35, route-specific entropy, positive/refusal controls; global pause/resume/status launcher routes use ITONAMI_DIR and run only through the pinned Amu native runtime; macOS runtime qualification remains open",
    }
    receipt_path = out / "build-receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(receipt_path.read_text(encoding="utf-8"), end="")


if __name__ == "__main__":
    main()
