"""Shared test-mechanism defaults, in seconds unless stated otherwise.

Consumers own workload budgets. Pass explicit overrides for slow I/O, animation
or soak checks rather than changing these defaults to accommodate one scenario.
"""

# ----------------------------------------------------------------------------------------------------------------------
# AUTHORSHIP INFORMATION - THIS FILE BELONGS TO MARC-ANDRE VOYER HELPER FUNCTIONS CODEBASE

__author__ = 'Marc-André Voyer'
__copyright__ = 'Copyright (C) 2020-2026, Marc-André Voyer'
__license__ = "MIT License"
__maintainer__ = 'Marc-André Voyer'
__email__ = 'marcandre.voyer@gmail.com'
__status__ = 'Production'

# ----------------------------------------------------------------------------------------------------------------------

POLL_INTERVAL = .1
WAIT_TIMEOUT = 10
ROTATION_TIMEOUT = 6
KEYBOARD_INTERVAL = .25
KEYBOARD_ATTEMPTS = 20
KEYBOARD_STABLE_SAMPLES = 3
SCREENSHOT_TIMEOUT = 15
WINDOW_DRAW_TIMEOUT = 10
