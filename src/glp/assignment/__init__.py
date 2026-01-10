"""Device Assignment Module.

This module provides functionality for bulk device assignment operations:
- Upload Excel files with serial numbers and MAC addresses
- Look up devices in database
- Present subscription/application/region options
- Intelligently patch only what's needed
- Resync with GreenLake and generate reports

Architecture: Clean Architecture with Hexagonal (Ports & Adapters)
"""
