# Verification

- Five mocked tests passed, including guarded selection and restoration, stale state and owner-only POSIX snapshot permissions under a permissive umask. Hermes plugin validation passed without warnings; this run did not touch an audio server.
- An earlier isolated PipeWire test failed once at startup and passed on a bounded retry, exercising two synthetic monitor sources. The host default was unchanged.
- Existing unmodified snapshots are not retroactively chmodded. Physical microphones, existing streams, recording, Windows, a reviewed demonstration and the full publication audit remain unverified.
