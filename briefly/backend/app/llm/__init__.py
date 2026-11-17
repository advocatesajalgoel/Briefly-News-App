"""Pluggable structured-extraction backends.

`rule_based` is the default: deterministic, offline, no credentials, and the
one the tests pin behaviour against. The hosted providers produce the same
schema and are put through the same grounding verification, so switching
provider cannot change what Briefly is allowed to assert.
"""
