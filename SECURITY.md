# Security Policy

## Supported version

Security fixes are provided for the latest published release of Zapret Hub Linux.
The project is currently tested only on Kali Linux.

## Reporting a vulnerability

Please do not publish credentials, private configuration, logs containing personal
data, or working exploit details in a public issue. Use GitHub's private
**Report a vulnerability** form in the repository Security tab. If the form is
unavailable, contact [@dosai_main](https://t.me/dosai_main) and share only the
minimum information needed to arrange a private report.

Include the affected version, Kali Linux version, reproduction steps and the
expected impact. Reports about bundled upstream components should also identify
the relevant upstream project when possible.

## Scope

Zapret Hub Linux runs local networking commands with narrowly scoped PolicyKit
permissions. Reports involving command injection, privilege escalation, unsafe
updates, leaked credentials or unintended network exposure are especially useful.
Never include real VPN subscriptions, proxy secrets or access tokens in reports.
