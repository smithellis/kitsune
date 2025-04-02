# PostgreSQL and PgBouncer

This document covers how PostgreSQL is configured in the kitsune application and how to use PgBouncer for connection pooling.

## PostgreSQL Configuration

Kitsune uses PostgreSQL as its primary database. The database connection is configured via the `DATABASE_URL` environment variable in the `.env` file, which is parsed using `dj-database-url`.

In the development environment, the PostgreSQL service runs in a Docker container and is accessible to the application via the `postgres` hostname.

## PgBouncer Connection Pooling

PgBouncer is a lightweight connection pooler for PostgreSQL. Instead of each Django process maintaining its own connection to the database, PgBouncer pools connections and reuses them effectively.

### Benefits of using PgBouncer

1. **Resource Efficiency**: Reduces the number of actual connections to the PostgreSQL server
2. **Connection Overhead**: Eliminates connection establishment overhead
3. **Performance**: Improves performance under high concurrency
4. **Reliability**: Handles connection failures gracefully

### How to Use PgBouncer in Development

The project includes PgBouncer configuration in the Docker Compose setup. To use it:

1. Make sure the PgBouncer service is included in your `docker-compose.yml` file
2. Use the provided toggle script to switch between direct PostgreSQL connection and PgBouncer:

```bash
./bin/toggle-pgbouncer.sh
```

3. Restart your application services

### Configuration Files

PgBouncer configuration files are located in the `docker/pgbouncer/` directory:

- `pgbouncer.ini`: Main configuration file
- `userlist.txt`: User authentication file

### Connection Settings

When using PgBouncer, the database connection string changes to:

```
postgres://kitsune:kitsune@pgbouncer:6432/kitsune
```

Instead of:

```
postgres://kitsune:kitsune@postgres:5432/kitsune
```

### Monitoring PgBouncer

You can monitor PgBouncer by connecting to its admin console:

```bash
psql -h localhost -p 6432 -U kitsune pgbouncer
```

Useful commands:
```sql
SHOW POOLS;
SHOW CLIENTS;
SHOW SERVERS;
SHOW STATS;
```

### Configuration Parameters

Key configuration parameters in `pgbouncer.ini`:

- `pool_mode`: How connections are handled (we use `transaction`)
- `max_client_conn`: Maximum number of client connections
- `default_pool_size`: Number of server connections to allow per user/database pair

The default settings should work well for most development work, but may need tuning in production environments.

### Production Considerations

For production use, consider:

1. Adjusting pool sizes based on your application's needs
2. Setting up monitoring for PgBouncer statistics
3. Configuring connection timeouts appropriately
4. Using a separate auth file with secure credentials 