"""Compatibility command: V8 trains three separate platform models.

The legacy shared periodic_model functions remain for migration tests only.
"""
from .platform_train import main

if __name__ == "__main__":
    main()
