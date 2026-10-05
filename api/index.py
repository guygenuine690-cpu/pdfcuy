"""Vercel entry point.

Vercel's Python runtime looks for an ASGI app in this file and serves it as one
function. The app object is imported rather than redefined so there is exactly
one copy of the routes, the middleware and the limits.
"""
import os
import sys

# app.py sits one level up, outside this directory.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app  # noqa: E402

__all__ = ["app"]
