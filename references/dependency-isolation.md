# Dependency isolation

First run `scripts/check_dependencies.py <target>` in plan mode. It discovers root `requirements*.txt` files and `scripts/requirements.txt` without installing anything.

After the user approves network access and the risk that package installation may execute build code, use `--create-venv`. The command creates a temporary virtual environment, installs the discovered requirements, runs `pip check`, optionally smoke-imports modules supplied through `--import`, records platform and Python versions, and removes the environment.

An isolated pass applies only to the reported operating system, architecture, Python version, indexes, and point in time. Require a CI matrix before claiming Windows, Linux, and macOS compatibility.
