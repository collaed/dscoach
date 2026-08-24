"""Service layer: business logic as pure functions of the database.

Each service module encapsulates domain logic for a specific concern.
Services are callable from BOTH routes AND background jobs (cron).
Services do NOT access request/session — they receive explicit parameters.
"""
