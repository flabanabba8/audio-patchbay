# Verification

- Six mocked tests passed, including guarded selection and restoration, stale state and owner-only POSIX snapshot permissions under a permissive umask. Native Windows Python 3.14 loaded the plugin and reported its POSIX requirement without contacting an audio server. Hermes plugin validation passed without warnings; these runs did not touch an audio server.
- An earlier isolated PipeWire test failed once at startup and passed on a bounded retry, exercising two synthetic monitor sources. The host default was unchanged.
- Existing unmodified snapshots are not retroactively chmodded. Physical microphones, existing streams, recording, Windows, a reviewed demonstration and the full publication audit remain unverified.
