# Releasing `renmori` to PyPI

The CLI publishes to PyPI from the `publish-pypi.yml` workflow using **PyPI
Trusted Publishing** (OpenID Connect) — there is no API token or stored secret
to manage. Publishing runs when you push a version tag (`v1.2.3`).

## One-time setup (PyPI side)

`renmori` is not on PyPI yet, so register a **pending** trusted publisher — the
first successful run creates the project.

1. First confirm the name is free: open <https://pypi.org/project/renmori/>. If
   it is taken, pick another distribution name and change `name` in
   `pyproject.toml` (the `renmori` import package and command can stay).
2. Sign in at <https://pypi.org> → **Account settings → Publishing → Add a new
   pending publisher**, and enter exactly:
   - **PyPI Project Name:** `renmori`
   - **Owner:** `MewBaka`
   - **Repository name:** `RenMori`
   - **Workflow name:** `publish-pypi.yml`
   - **Environment name:** *(leave blank)*
3. Save.

(For extra protection you can instead publish from a GitHub Environment: create
an environment named e.g. `pypi` in the repo, set `environment: pypi` on the
`publish` job, and put `pypi` in the Environment name field above — both sides
must match.)

## Each release

1. Bump `version` in `pyproject.toml` **and** `__version__` in
   `src/renmori/__init__.py` to the same value (PyPI rejects re-uploading a
   version).
2. Commit, then tag and push:

   ```bash
   git tag v1.0.0
   git push origin v1.0.0
   ```

3. The workflow builds the sdist + wheel, runs `twine check`, and publishes.
   Watch it under the repo's **Actions** tab.

After the first publish, users install with:

```bash
pip install renmori
```

## Notes

- The tag version and the `pyproject.toml` version should match (tag `v1.0.0`
  ↔ `version = "1.0.0"`).
- `workflow_dispatch` lets you run the build manually (for a dry run); it only
  publishes when a `v*` tag is the checked-out ref.
- This publishes the open CLI only. The closed poly plugin is distributed
  separately as prebuilt binaries from the GitHub release and is auto-downloaded
  by the CLI; see [usage.md](usage.md).
