"""Intent recognition package.

The similarity threshold lives here rather than in recognizer.py so that
the web layer and the tests can read it without importing
sentence-transformers.

One authoritative value: Phase 8A found the running application using
0.65 while the recognizer default, the voice controller, and every
automated recognition test used 0.60, so measurements taken against one
did not describe the other.
"""

DEFAULT_SIMILARITY_THRESHOLD = 0.65
