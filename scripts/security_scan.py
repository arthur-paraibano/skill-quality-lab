#!/usr/bin/env python3
"""Compatibility wrapper for the security scan command."""

from skill_quality_lab.security_scan import main

if __name__ == "__main__":
    raise SystemExit(main())
