"""
Elasticsearch compatibility module.

This module provides a consistent import layer for Elasticsearch functionality,
dynamically importing from either elasticsearch7 or elasticsearch8 packages
based on the configured ES_VERSION.

Note: The actual compatibility layer is now set up in SearchConfig.ready()
in kitsune/search/apps.py.
"""

# The compatibility layer is now implemented in SearchConfig.ready() method
# This file is kept for backwards compatibility and documentation
