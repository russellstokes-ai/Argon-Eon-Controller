# Upstream source snapshot
Source: https://github.com/JeffCurless/argoneon
Pinned commit: da5756a02a6409ec98b3aa8e3ceb8b40609a572d

Original Python files are preserved. sha256.json is checked before selected functions execute.
upstream_adapter.py selects OLED block transfer/reset/power functions and the RTC setter without running module-level GPIO/service setup. OLED exception handlers are changed to propagate errors rather than silently suppress them. Fan and cooling policy are separate HA OS adapter code. The complete upstream daemon, installer and late shutdown hook do not run.

The repository snapshot contains no declared licence file. Attribution is retained; no public GitHub repository was published by this task.
