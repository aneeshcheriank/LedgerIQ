# Docker Compose — LedgerIQ Dev Environment

```yaml
services:
  # 1. Your Python App / Dev Container
  app:
    build:
      context: .
      dockerfile: Dockerfile
    volumes:
      - ..:/workspace:cached
    # Keeps the container alive for VS Code connection
    command: sleep infinity
    environment:
      - VECTOR_DB_URL=http://qdrant:6333
      - PG_CONN_STR=postgresql://ledger:ledgerpass@postgres:5432/ledgerdb
    networks: 
      - dev-network

  # 2. Vector Database (e.g., Qdrant)
  qdrant:
    image: qdrant/qdrant:latest
    ports:
      - "6333:6333"
    volumes:
      - qdrant_data:/qdrant/storage
    networks: 
      - dev-network

  # 3. Persistent Storage for Parent Documents & Metadata
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: ledger
      POSTGRES_PASSWORD: ledgerpass
      POSTGRES_DB: ledgerdb
    ports:
      - "5432:5432"
    volumes:
      - pg_data:/var/lib/postgresql/data
    networks: 
      - dev-network

volumes:
  qdrant_data:
  pg_data:

networks:
  dev-network:
```

---

## Line-by-line explanation

### Service: `app` — Your Python dev container

```yaml
services:
```
Top-level key that defines all the containers (services) in this compose project.

```yaml
  app:
```
The name of your main service. `devcontainer.json` points to this with `"service": "app"`, so VS Code attaches to this container.

```yaml
    build:
      context: .
      dockerfile: Dockerfile
```
Instead of pulling a pre-built image, Docker builds this one from the `Dockerfile` in the same directory (`.` = `.devcontainer/`). This lets you customize your dev environment (install Python, uv, system packages, etc.).

```yaml
    volumes:
      - ..:/workspace:cached
```
Mounts your project root (`..` = `/home/aneesh/machine-learning-projects/LedgerIQ/`) into `/workspace` inside the container. The `:cached` flag tells Docker the host's view of the files is the source of truth — good for dev performance on macOS/Windows (no-op on Linux, but harmless).

```yaml
    command: sleep infinity
```
Overrides the Dockerfile's default command. `sleep infinity` keeps the container running indefinitely so VS Code can attach to it. Without this, the container would exit immediately after starting, and VS Code would have nothing to connect to.

```yaml
    environment:
      - VECTOR_DB_URL=http://qdrant:6333
      - PG_CONN_STR=postgresql://ledger:ledgerpass@postgres:5432/ledgerdb
```
Injects environment variables into the container:
- **`VECTOR_DB_URL`** — URL for your Qdrant vector database. Uses the service name `qdrant` as the hostname (Docker's internal DNS resolves service names to container IPs).
- **`PG_CONN_STR`** — PostgreSQL connection string. Same idea: `postgres` hostname resolves to the Postgres container. Format: `postgresql://user:password@host:port/database`.

```yaml
    networks:
      - dev-network
```
Connects this service to the `dev-network` (defined at the bottom). All services on the same network can talk to each other by service name.

---

### Service: `qdrant` — Vector database

```yaml
  qdrant:
    image: qdrant/qdrant:latest
```
Pulls the latest Qdrant image from Docker Hub. Qdrant is a vector database used for storing and searching embeddings (the numerical representations of your documents for RAG/semantic search).

```yaml
    ports:
      - "6333:6333"
```
Maps port 6333 from the container to port 6333 on your host machine. Lets you access Qdrant's API at `http://localhost:6333` from your browser or tools outside Docker.

```yaml
    volumes:
      - qdrant_data:/qdrant/storage
```
Mounts the named volume `qdrant_data` (defined at the bottom) to `/qdrant/storage` inside the container. This persists your vector data across container restarts/deletions — without it, all your embeddings would be lost when the container stops.

```yaml
    networks:
      - dev-network
```
Same network so `app` can reach Qdrant at `http://qdrant:6333`.

---

### Service: `postgres` — Relational database

```yaml
  postgres:
    image: postgres:16-alpine
```
Uses the official PostgreSQL 16 image based on Alpine Linux (a tiny, security-focused distro — keeps the image small).

```yaml
    environment:
      POSTGRES_USER: ledger
      POSTGRES_PASSWORD: ledgerpass
      POSTGRES_DB: ledgerdb
```
These are official Postgres image variables. On first start, the container automatically creates:
- A user named `ledger`
- With password `ledgerpass`
- And a database named `ledgerdb`

```yaml
    ports:
      - "5432:5432"
```
Exposes Postgres on your host's port 5432, so you can connect with tools like `psql`, DBeaver, or pgAdmin from your host machine.

```yaml
    volumes:
      - pg_data:/var/lib/postgresql/data
```
Persists the actual database files in the `pg_data` volume. All your tables and data survive container restarts.

```yaml
    networks:
      - dev-network
```
Same network — the `app` service connects to Postgres using the connection string `postgresql://ledger:ledgerpass@postgres:5432/ledgerdb`.

---

### Named volumes

```yaml
volumes:
  qdrant_data:
  pg_data:
```
Declares two Docker-managed volumes. These live on your host's filesystem (managed by Docker, typically under `/var/lib/docker/volumes/`) and outlive any single container. Think of them as external hard drives that you can plug into and unplug from containers.

---

### Network

```yaml
networks:
  dev-network:
```
Creates a custom bridge network. All three services join it, so they can communicate using their service names (`app`, `qdrant`, `postgres`) as hostnames. This keeps your dev stack isolated from other Docker projects on your machine.

---

## How it all fits together

```
┌─────────────────────────────────────────────┐
│  dev-network (internal Docker network)       │
│                                               │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐ │
│  │   app    │──▶│  qdrant  │   │ postgres │  │
│  │ (Python) │   │  :6333   │   │  :5432   │  │
│  │          │◀──│          │   │          │  │
│  └────┬─────┘   └──────────┘   └──────────┘  │
│       │                                        │
└───────┼────────────────────────────────────────┘
        │ volume: .. → /workspace (your code)
        │ volume: qdrant_data, pg_data (persistence)
        ▼
   Your host machine
```

Your Python code in `app` talks to Qdrant for vector search and Postgres for structured data — all three come up with one `docker compose up`.
