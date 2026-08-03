<div align="center">

# Zapret Hub Linux

A desktop control panel for Zapret, Zapret2, Happ and TG WS Proxy on Linux.

**Linux fork by [DosAi](https://github.com/DosAi)**<br>
[Repository](https://github.com/DosAi/Zapret-Hub-Linux) · [Telegram: @dosai_main](https://t.me/dosai_main)

</div>

> [!IMPORTANT]
> This is a **Linux-only** fork. Full functional testing is performed on
> **Kali Linux**; the installer is also smoke-tested in real Debian, Fedora,
> Arch and openSUSE containers.
> Windows is not supported: the repository does not ship `.exe` files, Windows
> installers or Windows instructions. Managed components require `systemd`;
> Alpine/OpenRC is deliberately unsupported for now.

[Русский README](README.md)

## What it is

Zapret Hub Linux is an experimental fork with native Linux backends based on
`systemd`, `nftables` and PolicyKit. It provides one interface for selecting a
Zapret strategy and controlling optional components. Porting, debugging, the
installer and tests were prepared by DosAi with help from **ChatGPT by OpenAI**.

## Version 3.2.0

- one-command installation of Zapret, Zapret2, Happ and TG WS Proxy;
- native Zapret and Zapret2 service control through `systemd` and `nftables`;
- strategy browsing without automatically activating the highlighted strategy;
- Happ can run independently and in parallel with Zapret or Zapret2;
- individual Happ and TG WS Proxy toggles on the main screen;
- local Telegram proxy plus a Telegram Desktop connection action;
- narrowly scoped PolicyKit authorization installed once;
- Linux-only repository and release archives with legacy Windows payloads removed.
- current Kali PolicyKit packages (`polkitd` and `pkexec`) instead of the removed
  `policykit-1` metapackage.
- experimental Debian/Ubuntu, Fedora, Arch and openSUSE installer support;
- verified official Happ packages in DEB, RPM and Arch formats;
- distribution-container smoke tests for dependency names and installer detection;
- corrected Linux `ping`, `/dev/null` and Happ version detection.

## Interface

![Main screen](docs/screenshots/main.png)

<details>
<summary>More screenshots</summary>

![Components](docs/screenshots/components.png)

![Service selection](docs/screenshots/services.png)

</details>

The screenshots are generated from the development preview and contain no user
configuration, subscriptions or credentials.

## Install on systemd Linux

Kali Linux remains the fully tested target. Debian/Ubuntu, Fedora, Arch and
openSUSE support is experimental and covered by installer/container smoke tests.

Zapret Hub Linux is not distributed through APT, DNF or AUR and does not ship
separate DEB/RPM application packages. The supported installation method is to
download the GitHub source tree and run the root `install.sh` script.

```bash
git clone --depth 1 https://github.com/DosAi/Zapret-Hub-Linux.git && cd Zapret-Hub-Linux && ./install.sh
```

The installer prepares dependencies, Zapret, Zapret2, Happ, TG WS Proxy, the
Python environment, Web UI, PolicyKit rule and desktop entry. It does not install
Telegram Desktop unless explicitly requested:

```bash
./install.sh --with-telegram
```

Preview the installation without changing the system:

```bash
./install.sh --dry-run --no-launch
```

The installer does not start, stop or restart existing networking services.
Existing Happ and third-party Zapret installations are preserved.

## Components

- [zapret](https://github.com/bol-van/zapret) and [zapret2](https://github.com/bol-van/zapret2)
- [zapret-discord-youtube-linux](https://github.com/Sergeydigl3/zapret-discord-youtube-linux)
- [tg-ws-proxy](https://github.com/Flowseal/tg-ws-proxy)
- [Happ Desktop](https://github.com/Happ-proxy/happ-desktop)
- [Zapret Hub upstream](https://github.com/goshkow/Zapret-Hub)

The upstream link is retained for attribution. This fork is not an official
upstream release. Bundled projects retain their own licenses and notices.

## Diagnostics and support

```bash
.venv/bin/zapret-hub-linux diagnose
.venv/bin/zapret-hub-linux start --dry-run
.venv/bin/pytest -q
```

See [README_LINUX.md](README_LINUX.md), [CONTRIBUTING.md](CONTRIBUTING.md) and
[SECURITY.md](SECURITY.md). Bugs and Kali Linux test results can be sent through
GitHub Issues or [@dosai_main](https://t.me/dosai_main).

## License

Linux fork changes are distributed under the [MIT License](LICENSE). Bundled
projects retain their own licenses and copyright notices.
