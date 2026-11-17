"""The processing pipeline.

    articles -> clustering -> fact extraction -> summarisation -> ranking -> QC

Everything downstream of fact extraction reads structured facts, never raw
article prose. That is what lets the card and the podcast stay consistent with
each other and with the sources.
"""
