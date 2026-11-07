"""Probe prior Darwin bridge lock diagnostics; not the new cron job entry.

Both prebuilt fixtures are supplied externally and content-pinned. The mutant
skips lock acquisition and demonstrates that this observer detects a bypass.
"""
import argparse
import fcntl
import hashlib
import os
from pathlib import Path
import subprocess
import tempfile


PINS = (
    "4582d5a6c5188d11b7aa925ddbaffc008859f93f4a4cdeae2b6c8a9c831c1324",
    "6aa50a37b8e9375c0085e1fd94ad03c9ffdb8bd8fcf9f9cd07901a52ef473e8e",
)


def main(fixture, mutant):
    for path, expected in zip((fixture, mutant), PINS):
        assert hashlib.sha256(path.read_bytes()).hexdigest() == expected
    with tempfile.TemporaryDirectory(prefix="awai-cron-lock-") as directory:
        root = Path(directory)
        (root / "test").mkdir()
        lock = root / "test" / "head.resident-lockfile"
        lock.touch(mode=0o600)
        fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
        saved = None
        if fd != 3:
            try:
                saved = os.dup(3)
            except OSError:
                pass
            os.dup2(fd, 3)
        lock_fd = os.open(lock, os.O_RDWR)
        try:
            def run(path):
                return subprocess.run([str(path)], cwd=root, pass_fds=(3,), capture_output=True,
                                      text=True, timeout=5)

            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            busy, bypass = run(fixture), run(mutant)
            assert busy.returncode == 1 and busy.stdout == "bridge/local-writer-busy\n" and not busy.stderr
            assert "command-executed\n" in bypass.stdout
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            free = run(fixture)
            assert free.returncode == 7 and free.stdout == "command-executed\n" and not free.stderr
            print("PASS prior Darwin fixture: busy refusal, bypass control, released admission")
        finally:
            os.close(lock_fd)
            if fd != 3:
                if saved is None:
                    os.close(3)
                else:
                    os.dup2(saved, 3)
                    os.close(saved)
            os.close(fd)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--mutant", type=Path, required=True)
    args = parser.parse_args()
    main(args.fixture.resolve(), args.mutant.resolve())
