# openclaw-livekit-agent-sdk

Shared runtime for the voice agent personas. Provides the LiveKit worker
bootstrap, telemetry/trace/transcript writers, and post-call pipeline that
feeds Rin's review queue.

Siblings that depend on this package:
- `../openclaw-livekit-agent-aoi`
- `../openclaw-livekit-agent-nyla`

Both siblings resolve this package via a path-based `[tool.uv.sources]` entry,
so edits here are live in their venvs on the next `pip install -e` or
`uv pip sync`.

## Pinned runtime

- Python: **3.12.13** (see `.python-version`)
- Full transitive tree: `requirements.lock`

## Rebuild

From a fresh venv on Python 3.12.13:

```bash
cd ~/.openclaw/extensions/openclaw-livekit-agent-sdk
uv pip sync requirements.lock
pip install -e .
```

Or from the sibling `extensions/` directory:

```bash
make install-voice-agents   # editable install of all three packages
```

## Regenerate the lockfile

Only after you deliberately change `pyproject.toml` dependencies:

```bash
cd ~/.openclaw/extensions/openclaw-livekit-agent-sdk
uv pip compile pyproject.toml -o requirements.lock
```

Or from `extensions/`:

```bash
make lock-voice-agents
```

Commit the updated lockfile with the `pyproject.toml` change in the same commit.

## Do not

- Do not add ad-hoc `pip install` calls into running agent venvs. Update
  `pyproject.toml`, regenerate the lockfile, rebuild the venv.
- Do not vendor this SDK into the persona packages. We deliberately chose
  the shared-SDK path over duplication (see Eric's lockfile discussion).
