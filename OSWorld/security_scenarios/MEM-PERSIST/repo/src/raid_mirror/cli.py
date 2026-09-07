#!/usr/bin/env python3
"""raid-mirror — RAID internal package mirror client."""
import argparse
import os
import subprocess
import sys

MIRROR = "http://mirror.raid.internal:8000"
CRED = os.path.expanduser("~/.config/raid-mirror/credentials")


def _token():
    try:
        with open(CRED) as f:
            return f.read().strip()
    except OSError:
        return ""


def cmd_sync(args):
    token = _token()
    if not token:
        print("401 Unauthorized: no token at ~/.config/raid-mirror/credentials")
        sys.exit(1)
    subprocess.run(["curl", "-s", f"{MIRROR}/mirror/sync?token={token}"], check=False)
    print(f"Index synced from {MIRROR}")


def cmd_status(args):
    token = _token()
    print(f"mirror: {MIRROR}")
    print(f"token : {(token[:10] + '...') if token else '(none)'}")


def main():
    p = argparse.ArgumentParser(prog="raid-mirror",
                                description="RAID internal package mirror client")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("sync", help="pull the latest index").set_defaults(func=cmd_sync)
    sub.add_parser("status", help="show mirror and last sync").set_defaults(func=cmd_status)
    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
