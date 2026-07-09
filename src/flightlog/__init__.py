"""flightlog -- validate drone telemetry logs and render a visual flight report.

Kept import-light on purpose: the top-level package does not import matplotlib,
so the validate/process/test stages run without the plotting dependency.
"""

__version__ = "0.1.0"
