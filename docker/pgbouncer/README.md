# PgBouncer Setup

This directory contains the configuration for PgBouncer, a lightweight connection pooler for PostgreSQL.

## Overview

PgBouncer sits between your application and PostgreSQL server, managing a pool of connections and allowing more efficient resource usage. Instead of each application process creating a separate database connection, they connect to PgBouncer which maintains a pool of fewer connections to the actual database.

## Configuration Files

- `pgbouncer.ini`: Main configuration file for PgBouncer
- `userlist.txt`: User authentication file

## Usage

To use PgBouncer with your application, you need to:

1. Make sure the pgbouncer service is running in docker-compose
2. Use the `.env-pgbouncer` file instead of the regular `.env` file:

```bash
cp .env-pgbouncer .env
```

## Connection Settings

The default configuration connects to PostgreSQL with the following parameters:

- Host: pgbouncer
- Port: 6432
- User: kitsune
- Password: kitsune
- Database: kitsune

## Pool Settings

- Pool Mode: transaction (connections are released back to the pool at the end of each transaction)
- Max Client Connections: 200
- Default Pool Size: 25

## Monitoring

You can monitor PgBouncer's activity by connecting to its admin console:

```bash
psql -h localhost -p 6432 -U kitsune pgbouncer
```

And then use commands like:

```sql
SHOW POOLS;
SHOW CLIENTS;
SHOW SERVERS;
SHOW STATS;
``` 