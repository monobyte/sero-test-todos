#!/usr/bin/env python3
"""
Basic import test to verify project structure.
Run this before installing dependencies to check for syntax errors.
"""
import sys
from pathlib import Path

def test_imports():
    """Test that all modules can be imported."""
    errors = []
    
    modules = [
        "config",
        "main",
        "models.base",
        "models.market",
        "routers.health",
        "utils.cache",
        "utils.rate_limiter",
        "utils.logger",
    ]
    
    print("Testing module imports...\n")
    
    for module in modules:
        try:
            __import__(module)
            print(f"✓ {module}")
        except Exception as e:
            print(f"✗ {module}: {e}")
            errors.append((module, str(e)))
    
    print(f"\n{'='*50}")
    if errors:
        print(f"❌ {len(errors)} import error(s) found:")
        for module, error in errors:
            print(f"  - {module}: {error}")
        return False
    else:
        print("✅ All imports successful!")
        return True

if __name__ == "__main__":
    success = test_imports()
    sys.exit(0 if success else 1)
