"""Tiers 0-3 of the retrieval pipeline: search, assess, probe, validate -- as code that runs.

    python -m discover.run --out data/discover

Every stage writes a machine-checkable artifact and every accept/reject is a
deterministic predicate. An LLM may *propose* (the rubric hook in ``rubric.py``
reads ``DISCOVER_LLM``); code disposes. Without a key the rubric is filled from
registry metadata and the live probe alone, which is what ran for the record.
"""
