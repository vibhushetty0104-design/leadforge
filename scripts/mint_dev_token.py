"""Mint a short-lived access token for calling the API locally (e.g. with curl).

Only works with the HS256 secret of a *local* Supabase stack (``supabase start``
prints it as "JWT secret") and refuses to run in staging/production. Hosted
Supabase projects should use a real sign-in instead.

    python scripts/mint_dev_token.py --user-id <uuid> [--email you@example.com]
"""

from __future__ import annotations

import argparse
import os
import sys
import time
import uuid

import jwt


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--user-id", type=uuid.UUID, required=True)
    parser.add_argument("--email", default=None)
    parser.add_argument("--minutes", type=int, default=30, choices=range(1, 61), metavar="1-60")
    args = parser.parse_args()

    if os.environ.get("ENVIRONMENT", "development").lower() in {"staging", "production"}:
        sys.exit("Refusing to mint tokens outside development.")
    secret = os.environ.get("SUPABASE_JWT_SECRET")
    supabase_url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    if not secret or not supabase_url:
        sys.exit("SUPABASE_JWT_SECRET and SUPABASE_URL must be set (see .env.example).")

    now = int(time.time())
    claims = {
        "sub": str(args.user_id),
        "aud": "authenticated",
        "role": "authenticated",
        "iss": f"{supabase_url}/auth/v1",
        "iat": now,
        "exp": now + args.minutes * 60,
    }
    if args.email:
        claims["email"] = args.email
    print(jwt.encode(claims, secret, algorithm="HS256"))


if __name__ == "__main__":
    main()
