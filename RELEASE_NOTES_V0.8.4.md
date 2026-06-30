# Armilar v0.8.4 experimental global price completion

Version 0.8.4 implements the deterministic completion and validation engine for
the canonical ARM01-ARM09 global price grid.

It preserves direct P1/P2 observations, anchors fallbacks to each target
economy's official headline inflation, estimates only the category deviation,
chains monthly indices, publishes uncertainty and validates the methods by
leave-one-economy-out reconstruction.

This code does not represent synthetic fixtures as a real global release.
Production execution still requires acquired official observations and
ratified validation gates.

Both release flags remain false.
