"""Evaluation harnesses for the evaluator's own LLM call sites.

Distinct from ``grading/`` (which grades the TRADING system) and from
``director/retro.py`` (which grades one week's plan against the next card):
this package grades the *arms* a call site could be served by, against each
other, on the same inputs — `champion-challenger-policy.md` §3.
"""
