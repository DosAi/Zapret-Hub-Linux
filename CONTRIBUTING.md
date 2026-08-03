# Contributing to Zapret Hub Linux

Thank you for helping improve the project. The fork is Linux-only. Full
functional testing currently targets Kali Linux; installer support for
Debian/Ubuntu, Fedora, Arch and openSUSE is experimental and covered by
distribution-container smoke tests.

## Before opening a change

- Search existing issues and pull requests.
- Keep changes focused on the Linux application and its bundled Linux runtimes.
- Do not add Windows payloads, installers, executables or platform instructions.
- Do not commit logs, local settings, VPN subscriptions, proxy secrets, tokens or
  credentials.
- Preserve third-party license and attribution files.

## Development setup

```bash
git clone --depth 1 https://github.com/DosAi/Zapret-Hub-Linux.git
cd Zapret-Hub-Linux
./install.sh --dry-run --no-launch
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
cd web_ui && npm ci && cd ..
```

Run the checks before submitting a pull request:

```bash
.venv/bin/pytest -q
npm --prefix web_ui run build
bash -n install.sh scripts/*.sh
```

Do not start, stop or restart networking services as part of automated tests.
Describe the distribution and version used for any manual verification. Testing
on Kali Linux is especially valuable; reports from the experimental
Debian/Ubuntu, Fedora, Arch and openSUSE paths are also welcome.

## Pull requests

Explain what changed, why it is needed and how it was verified. Keep generated
files and vendored component updates separate from application logic when
possible. By submitting a contribution, you agree that it can be distributed
under the repository's MIT license while bundled projects retain their own
licenses.
