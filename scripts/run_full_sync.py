#!/usr/bin/env python3
from __future__ import annotations

import argparse

import httpx


def main() -> None:
    parser = argparse.ArgumentParser(description="Trigger a full sync job via internal API")
    parser.add_argument("source_id")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--token", default="")
    args = parser.parse_args()

    headers = {"X-Internal-Token": args.token} if args.token else {}
    response = httpx.post(
        f"{args.base_url}/internal/sources/{args.source_id}/sync",
        headers=headers,
        json={"mode": "full", "operator": "script"},
        timeout=10.0,
    )
    response.raise_for_status()
    print(response.json())


if __name__ == "__main__":
    main()
