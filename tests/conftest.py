"""
conftest.py — shared pytest setup for Phase 6 tests.
Adds backend/ to sys.path so all backend modules are importable.
"""
import sys
import os

# Make backend importable without installing the package
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
