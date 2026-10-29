"""Shared test-mechanism defaults, in seconds unless stated otherwise.

Consumers own workload budgets. Pass explicit overrides for slow I/O, animation
or soak checks rather than changing these defaults to accommodate one scenario.
"""

POLL_INTERVAL = .1
WAIT_TIMEOUT = 10
ROTATION_TIMEOUT = 6
KEYBOARD_INTERVAL = .25
KEYBOARD_ATTEMPTS = 20
KEYBOARD_STABLE_SAMPLES = 3
SCREENSHOT_TIMEOUT = 15
WINDOW_DRAW_TIMEOUT = 10
