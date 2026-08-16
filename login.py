#!/usr/bin/env python3
"""Login to Naukri and save session."""
import sys
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.auth import NaukriAuth


def main():
    email = os.getenv("NAUKRI_EMAIL")
    password = os.getenv("NAUKRI_PASSWORD")

    if not email or not password:
        print("Fill in NAUKRI_EMAIL and NAUKRI_PASSWORD in .env file")
        sys.exit(1)

    auth = NaukriAuth(email, password, Path("session.json"))
    success = auth.login()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()