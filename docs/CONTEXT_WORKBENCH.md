# Context Workbench

Open Compressor from the NSCP desktop header or run nscp-context-gui.
The workbench explicitly opens JSON message files, plans with a bounded
deterministic or lexical route, verifies original references and metadata,
shows estimated before/after context size, and allows exact paginated recall
from the loaded original. Export only a new file for a verified fitting
plan. It never overwrites input files, modifies Hermes, calls models, or
installs resources. The Engine tab inspects resource presence only.
The CLI uses the same bounded JSON reader (4 MiB, 4096 messages, no duplicate
fields/nonfinite numbers). A user may use a different explicit request file
than the original transcript. This GUI is an initial functional workbench,
not a live Hermes control panel or measured provider-token dashboard.
