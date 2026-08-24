"""Repository layer: SQL queries wrapped in callable functions.

Each repo module contains all SQL for a specific domain entity.
Repos do NOT make business decisions (no if/else on statuses).
They read and write data, nothing more.
"""
