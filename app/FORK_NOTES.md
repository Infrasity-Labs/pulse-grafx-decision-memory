# Fork notes

This folder is a copy of the tracked files of
[nsidnev/fastapi-realworld-example-app](https://github.com/nsidnev/fastapi-realworld-example-app).

- Upstream commit: `029eb7781c60d5f563ee8990a0cbfb79b244538c` (2022-08-21).
- License: MIT. The upstream `LICENSE` file is kept unchanged in this folder.
- Copied on 2026-10-29 with `git ls-files`, so no `.git` folder and no untracked files.
- No source file was edited. Line numbers cited in the demo refer to this copy.
- Files that only build, deploy or test the app in a container were removed, because nothing in this repo reads them: `poetry.lock`, `Dockerfile`, `docker-compose.yml`, `.dockerignore`, `alembic.ini`, `postman/`, `scripts/` and `.github/`. `README.rst` still mentions some of them. They are in the upstream commit above. `pyproject.toml`, `setup.cfg`, `tests/` and `app/` stay, because the recorded run reads and cites them.
- The app is never run. Postgres is not needed. Agents only read the code.
- `pyproject.toml` still carries the upstream author line, because this is a plain copy.
