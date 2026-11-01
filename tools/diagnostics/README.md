# Manual hardware diagnostics

These scripts were used during development to probe real oscilloscopes. They
are **not part of the automated test suite** (`pytest.ini` only collects
`tests/`) and may change the instrument state.

Run them explicitly, from the project root, after activating the virtual
environment and connecting the scope:

```bash
python tools/diagnostics/test_integration.py
python tools/diagnostics/test_usbtmc_raw.py
python tools/diagnostics/test_usbtmc_simple.py
python tools/diagnostics/test_waveform.py
```

Some scripts contain hard-coded resource names or USB identifiers from the
development bench. Edit the resource string at the top of the script or pass it
on the command line when supported.

For the automated, hardware-free suite use:

```bash
python -m pytest tests -q
```
