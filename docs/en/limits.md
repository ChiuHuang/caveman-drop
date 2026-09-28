# Limits

Up front (the upload page says the same thing):

- **Per file:** 5 GB by default for public uploads, uncapped once signed in.
- **Shared folders:** the cap is on traffic per time window, not on stored
  total — 5 GB per 10 minutes per folder by default. Going over slows you down,
  it never deletes anything.
- **Rate limit:** 30 uploads per IP per hour by default, then `429`.
- **Fair use:** a burst of uploads is slowed down automatically (starting at
  90 Mbps, minus 10 for every extra GB, floor 40). Signed-in sessions are
  exempt.
- **Public shares are unauthenticated:** anyone who knows a folder id can add
  files to it, so only share with people you trust.

Source: <https://github.com/ChiuHuang/caveman-drop>
