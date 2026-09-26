# Limits & fair use

Configured via `.env` (see `.env.example`).

- **Max single file:** `MAX_FILE_SIZE_GB` (default 5 GB), always enforced —
  streaming writes abort and clean up past the cap.
- **Multi-file folders:** once a folder holds more than one file, its combined
  size is capped at `MAX_MULTI_FOLDER_TOTAL_GB` (default 1 GB). Single-file
  folders are only bound by the per-file cap. Concurrent uploads to one folder
  are serialized so the quota can't be raced.
- **Rate limit:** `RATE_LIMIT_MAX_UPLOADS` uploads per IP per
  `RATE_LIMIT_WINDOW_SECONDS` (default 30/hour). Exceeding it returns `429`.
- **CORS:** the public API accepts cross-origin calls, so browser JS on any
  site and AI agents can upload directly.
- **No auth on public shares:** anyone with a folder id can add files to it.
  Treat folder ids as bearer tokens and only share them deliberately.
