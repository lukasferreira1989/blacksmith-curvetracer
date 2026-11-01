# Windows executable test helpers

These scripts run the executable produced by `build_windows.bat`. They do not
build anything.

- **`test_exe.bat`** — runs `dist\CurveTracer\CurveTracer.exe` and prints the
  last lines of the log.
- **`test_run.bat`** — runs the executable with stderr redirected to
  `error.log` and shows the exit code.

Both scripts change to the project root (`%~dp0..\..`), so they work when
double-clicked or invoked from any directory.
