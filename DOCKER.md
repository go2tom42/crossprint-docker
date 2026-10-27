# Run Crossprint with Docker Compose

## 1. Get the source

```sh
git clone https://github.com/ELI7F/crossprint.git
cd crossprint
```

Copy `Dockerfile`, `compose.yaml`, `.dockerignore`, and optionally
`.env.example` from this package into the repository root, replacing files
if you have already created equivalents.

## 2. Build and start

```sh
docker compose up -d --build
```

Open <http://localhost:5000> (or `http://SERVER-IP:5000` from another
machine on your LAN).

## 3. Check status and logs

```sh
docker compose ps
docker compose logs -f crossprint
docker compose exec crossprint python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:5000/healthz').read().decode())"
```

## 4. Stop, update, or change the port

```sh
docker compose down
git pull
docker compose up -d --build
```

To use a different host port, create `.env` from `.env.example` and set,
for example, `CROSSPRINT_PORT=8085`; then run `docker compose up -d`.
The app will be available on port 8085 on the host.

## Upload limits and storage

The defaults here are `MAX_UPLOAD_MB=600` and
`MAX_UNCOMPRESSED_MB=3072`, matching the repository's hosted deployment
configuration. Adjust these in `.env` if needed. For large conversions,
make sure the Docker host has sufficient free temporary disk space.

The app does not persist uploaded projects as a library; conversion uploads
and results are temporary. Do not add a persistent volume unless you have a
specific need to change that behavior.

## Notes

- Compose builds the image from the checked-out repository, including its
  bundled printer presets and policy files.
- The container runs Gunicorn with one worker, two threads, and a 600-second
  timeout, matching the project's deployment configuration.
- This service has no built-in authentication. Keep it on a trusted LAN or
  put it behind an authenticated reverse proxy before exposing it to the
  internet.
- Review the project's `LICENSE` and `NOTICE.md` before redistributing or
  publicly hosting it. The repository documents AGPL obligations for its
  bundled preset data.
