#!/usr/bin/env python3
"""Observe the normal Agent launcher against an isolated synthetic adapter."""
import argparse
import hashlib
import http.server
import json
import os
from pathlib import Path
import secrets
import shutil
import signal
import subprocess
import tempfile
import threading
import time

ROOT = Path(__file__).resolve().parents[2]
MODEL = "inkling-2-mini-gyomu-qa"
SCHEMA = "768859620bef185169b794b3ca1dbabb0de8e96186c61e698e61418afd27a034"
PROFILE = "awai-hiring-ops"
PROFILE_PATH = Path("profiles") / PROFILE / "itonami.edn"
DRAFT = "架空の求人：果樹園スタッフ 🌱\n仕事は苗木の手入れです。\n"
SYSTEM = "Draft only. Use fictional data and no tools. Never publish or contact anyone."
OPENSSL = "/usr/bin/openssl"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, value):
    path.write_bytes(json.dumps(value, sort_keys=True).encode() + b"\n")


class Listener(http.server.BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def do_POST(self):
        request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        authentic = self.headers.get_all("Authorization") == [f"Bearer {self.server.bearer}"]
        valid = (self.path == "/v1/chat/completions" and request == {
            "model": MODEL, "messages": [{"role": "system", "content": SYSTEM},
                {"role": "user", "content": self.server.input}],
            "stream": False, "temperature": 0, "max_tokens": 96,
        })
        self.server.observations.append((authentic, valid))
        mode = self.server.mode
        if mode == "slow":
            time.sleep(4)
        elif mode == "delayed-completion":
            time.sleep(16)
        response = {"model": MODEL, "choices": [{"index": 0,
            "message": {"role": "assistant", "content": DRAFT}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 63, "completion_tokens": 27, "total_tokens": 90}}
        if mode == "wrong-model":
            response["model"] = "different-model"
        elif mode == "tool":
            response["choices"][0]["message"]["tool_calls"] = [{"id": "unavailable"}]
        elif mode == "length":
            response["choices"][0]["finish_reason"] = "length"
        elif mode == "context":
            response["usage"] = {"prompt_tokens": 513, "completion_tokens": 27, "total_tokens": 540}
        status = 200 if authentic and valid else 401
        body = b'{"model":' if mode == "malformed" else json.dumps(response).encode()
        try:
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            if mode != "slow":
                raise


def run(launcher, env, profile, grant, approval, signature, output, auth):
    args = [launcher, "turn", "hiring-qa", profile, grant, approval, signature, output]
    with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
        actions = [(os.POSIX_SPAWN_DUP2, stdout.fileno(), 1), (os.POSIX_SPAWN_DUP2, stderr.fileno(), 2)]
        if auth is not None:
            read_fd, write_fd = os.pipe()
            try:
                assert os.write(write_fd, auth) == len(auth)
            finally:
                os.close(write_fd)
            actions.append((os.POSIX_SPAWN_DUP2, read_fd, 4))
        try:
            pid = os.posix_spawn(str(launcher), list(map(str, args)), env, setpgroup=0, file_actions=actions)
        finally:
            if auth is not None:
                os.close(read_fd)
        start = time.monotonic()
        while True:
            done, status = os.waitpid(pid, os.WNOHANG)
            if done:
                break
            if time.monotonic() - start > 30:
                os.killpg(pid, signal.SIGKILL)
                os.waitpid(pid, 0)
                raise AssertionError("launcher exceeded fixture deadline")
            time.sleep(0.02)
        stdout.seek(0)
        stderr.seek(0)
        return os.waitstatus_to_exitcode(status), stdout.read(), stderr.read(), time.monotonic() - start


def main(amu_source, preflight_package, output):
    dirty = subprocess.check_output(["git", "-C", amu_source, "status", "--porcelain", "--", "seed", "scripts/seed"])
    assert not dirty, "the Amu fixture source checkout must match the pin"
    output.mkdir(mode=0o700)
    package = output / "package"
    subprocess.run([ROOT / "bin/build-macos-hiring-qa", amu_source, preflight_package, package],
                   check=True, timeout=120)
    pkg = package / "hiring-qa"
    rebuild = output / "rebuild"
    subprocess.run([ROOT / "bin/build-macos-hiring-qa", amu_source, preflight_package, rebuild],
                   check=True, timeout=120, stdout=subprocess.DEVNULL)
    assert sha(pkg / "guest.macho") == sha(rebuild / "hiring-qa/guest.macho")
    print("PASS reproducible signed guest", flush=True)
    launcher = package / "bin/itonami-agent"
    stage = output / "amu-fixture"
    approval_private = subprocess.check_output([OPENSSL, "ecparam", "-name", "prime256v1", "-genkey", "-noout"])
    public = subprocess.check_output([OPENSSL, "ec", "-pubout"], input=approval_private, stderr=subprocess.DEVNULL)
    bearer = secrets.token_hex(32)
    fixture = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Listener)
    fixture.bearer = bearer
    fixture.mode = "ok"
    fixture.input = (pkg / "input.txt").read_text()
    fixture.observations = []
    service = threading.Thread(target=fixture.serve_forever, daemon=True)
    service.start()

    profile_store = output / "store"
    (profile_store / PROFILE_PATH).parent.mkdir(parents=True)
    profile_file = profile_store / PROFILE_PATH
    shutil.copyfile(ROOT / "itonami" / PROFILE_PATH, profile_file)
    profile_bytes = profile_file.read_bytes()
    fake_loader = output / "legacy-loader"
    fallback = output / "legacy-invoked"
    fake_loader.write_text('#!/bin/sh\n: > "$LEGACY_MARKER"\nexit 99\n')
    fake_loader.chmod(0o700)
    env = {"PATH": "/usr/bin:/bin", "LANG": "C", "ITONAMI_DIR": str(profile_store),
           "KEXE_LOADER": str(fake_loader), "LEGACY_MARKER": str(fallback)}
    cases = []
    registration = pkg / "registration.json"
    guest = pkg / "guest.macho"
    guest_bytes = guest.read_bytes()
    guest_sha = sha(guest)
    build_path = pkg / "build.json"
    endpoint = f"http://127.0.0.1:{fixture.server_port}"

    def case(name, *, expected=2, reason=None, auth=bearer.encode(), profile=PROFILE, change_grant=None,
             change_approval=None, broken_signature=False, missing_grant=False, tamper_grant=False, use=None, mode="ok",
             seconds=12, requests=0, calls=None, authentic=True):
        folder = output / name
        folder.mkdir()
        issued = folder / "issued.klg"
        approval = folder / "approval.json"
        signature = folder / "approval.sig"
        dest = folder / "result"
        if use is not None:
            issued, approval, signature = [output / use / p.name for p in (issued, approval, signature)]
        else:
            grant = (f"KLG1\nartifact={guest_sha}\nwire=11\nschema={SCHEMA}\nprofile=amu-program-llm-v1\n"
                     f"provider=murakumo-qa-v1\nendpoint={endpoint}\nmodel=:{MODEL}\nseconds={seconds}\ntokens=96\n")
            if change_grant:
                grant = grant.replace(*change_grant)
            if not missing_grant:
                issued.write_bytes(grant.encode())
            approval_data = {"schema": "itonami.hiring-qa-approval.v1", "decision": "approve",
                "run": secrets.token_hex(16), "profile": PROFILE, "profileSha256": hashlib.sha256(profile_bytes).hexdigest(),
                "buildSha256": sha(build_path), "policySha256": sha(registration) if registration.is_file() else "0" * 64,
                "grantSha256": hashlib.sha256(grant.encode()).hexdigest(), "expiresAt": int(time.time()) + 180}
            approval_data.update(change_approval or {})
            write_json(approval, approval_data)
            sig = subprocess.check_output([OPENSSL, "dgst", "-sha256", "-sign", "/dev/stdin", approval], input=approval_private)
            signature.write_bytes(b"wrong" if broken_signature else sig)
            if tamper_grant:
                issued.write_bytes(grant.replace("tokens=96", "tokens=95").encode())

        fixture.mode = mode
        count = len(fixture.observations)
        code, stdout, stderr, elapsed = run(launcher, env, profile, issued, approval, signature, dest, auth)
        assert bearer.encode() not in stdout + stderr and not fallback.exists(), name
        assert code == expected and not stdout and (reason is None or reason.encode() in stderr), (name, code, expected)
        observed = fixture.observations[count:]
        assert observed == [(authentic, True)] * requests, (name, observed)
        draft_file = dest / "draft.txt"
        import_file = dest / "draft.edn"
        receipt_file = dest / "receipt.json"
        receipt = json.loads(receipt_file.read_bytes()) if receipt_file.exists() else None
        if calls is not None:
            assert receipt["providerCalls"] == calls and receipt["synthetic"] is True, name
        if code == 0:
            assert draft_file.read_bytes() == DRAFT.encode() and import_file.is_file(), name
            assert receipt["schema"] == "itonami.hiring-qa-turn.v1" and receipt["classification"] == "pass", name
            assert receipt["draft"] == {"sha256": sha(draft_file), "bytes": len(DRAFT.encode())}, name
            assert receipt["usage"] == {"inputTokens": 63, "outputTokens": 27} and receipt["finishReason"] == "stop", name
            assert receipt["grant"]["sha256"] == sha(issued) and receipt["approval"]["sha256"] == sha(approval), name
            assert receipt["artifacts"]["amuRegisteredLauncher"] == sha(pkg / "amu/amu-cli.macho"), name
            assert receipt["endpointPolicy"]["sha256"] == sha(registration), name
        else:
            assert not draft_file.exists() and not import_file.exists(), name
            assert receipt is None or (receipt["classification"] != "pass" and receipt["draft"] is None), name
        if mode == "slow":
            assert elapsed < 4, "agent waited for delayed listener"
        elif mode == "delayed-completion":
            assert 16 <= elapsed < seconds, "completion did not fit the independently authorized deadline"
        cases.append({"case": name, "exit": code, "httpRequests": len(observed), "providerCalls": calls,
                      "elapsedMilliseconds": round(elapsed * 1000)})
        print(f"PASS {name} (exit {code}, HTTP {len(observed)})", flush=True)

    try:
        case("unregistered", expected=78, reason="registration unavailable")
        subprocess.run(["basilisp", "run", "-p", "scripts/seed", "scripts/seed/stage-macos-murakumo-fixture.cljc",
                        "--", stage, str(fixture.server_port)], cwd=amu_source, check=True, timeout=120)
        fixture_cli = pkg / "amu/amu-cli.macho"
        shutil.copy2(stage / "amu-cli.macho", fixture_cli)
        key = pkg / "approval-key.pem"
        key.write_bytes(public)
        policy = {"schema": "itonami.hiring-qa-registration.v1", "mode": "synthetic", "issuer": "synthetic-qa-test",
                  "port": fixture.server_port, "launcherSha256": sha(fixture_cli), "keySha256": sha(key)}
        write_json(registration, {**policy, "mode": "approved", "residentSha256": "0" * 64, "weightsSha256": "0" * 64})
        case("unprotected-approved-mode", expected=78, reason="approved package must be protected")
        write_json(registration, policy)
        case("completion", expected=0, calls=1, requests=1)
        case("replayed-approval", use="completion", reason="approval already consumed")
        case("wrong-profile", profile="different-profile", reason="profile refused")
        profile_file.write_bytes(profile_bytes + b"\n")
        case("changed-profile", reason="profile preflight refused")
        profile_file.write_bytes(profile_bytes)
        guest.write_bytes(guest_bytes + b"\n")
        case("changed-artifact", expected=78, reason="build artifact pin mismatch")
        guest.write_bytes(guest_bytes)
        case("missing-grant", missing_grant=True, reason="grant or approval unavailable")
        case("bad-signature", broken_signature=True, reason="approval signature refused")
        case("tampered-signed-grant", tamper_grant=True, reason="approval scope or expiry refused")
        case("denied-approval", change_approval={"decision": "deny"}, reason="approval scope or expiry refused")
        case("expired-approval", change_approval={"expiresAt": int(time.time()) - 10}, reason="approval scope or expiry refused")
        case("approval-shorter-than-grant", change_approval={"expiresAt": int(time.time()) + 8}, reason="approval expires before")
        case("wrong-build-approval", change_approval={"buildSha256": "0" * 64}, reason="approval scope or expiry refused")
        for name, old, new in (
            ("invalid-grant", "KLG1", "KLG2"), ("wrong-grant-artifact", guest_sha, "0" * 64),
            ("wrong-endpoint", endpoint, "http://127.0.0.1:1"), ("wrong-grant-model", MODEL, "different-model"),
            ("zero-tokens", "tokens=96", "tokens=0"), ("excess-tokens", "tokens=96", "tokens=97"),
            ("excess-deadline", "seconds=12", "seconds=91"),
        ):
            case(name, change_grant=(old, new), reason="KLG1 scope or budget refused")
        write_json(registration, {**policy, "port": 1})
        case("different-registered-port", change_grant=(endpoint, "http://127.0.0.1:1"), expected=69, calls=0)
        write_json(registration, policy)
        case("missing-credential", auth=None, expected=69, calls=0)
        case("listener-refusal", auth=b"x".hex().encode() * 32, authentic=False, expected=1, calls=1, requests=1)
        for mode in ("malformed", "wrong-model", "tool", "length", "context"):
            case(mode, mode=mode, expected=1, calls=1, requests=1)
        case("deadline", mode="slow", seconds=1, expected=124, calls=1, requests=1)
        case("delayed-completion", mode="delayed-completion", seconds=25, expected=0, calls=1, requests=1)
    finally:
        fixture.shutdown()
        fixture.server_close()
        service.join()
    assert bearer.encode() not in fixture_cli.read_bytes() and approval_private not in fixture_cli.read_bytes()
    write_json(output / "gate.json", {"synthetic": True, "reproducibleGuestSha256": guest_sha, "cases": cases,
        "completionReceiptSha256": sha(output / "completion/result/receipt.json")})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("amu_source", type=Path)
    parser.add_argument("preflight_package", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    main(args.amu_source.resolve(), args.preflight_package.resolve(), args.output.resolve())
