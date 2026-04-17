# 🐳 Docker Compose Setup Guide

## Module 3: PostgreSQL 16 + Redis 7

This guide shows how to start the database services for Kisan AI.

---

## Prerequisites

- Docker installed ([docker.com/download](https://www.docker.com/products/docker-desktop))
- Docker Compose (included with Docker Desktop)
- Verify installation:
  ```bash
  docker --version
  docker-compose --version
  ```

---

## Starting Services

### 1. Start PostgreSQL + Redis

```bash
cd ~/projects/kisan-ai
docker-compose up -d
```

You should see:
```
Creating kisan_ai_postgres ... done
Creating kisan_ai_redis ... done
```

### 2. Check Service Status

```bash
docker-compose ps
```

Expected output:
```
NAME                 STATUS              PORTS
kisan_ai_postgres    Up (healthy)        5432/tcp
kisan_ai_redis       Up (healthy)        6379/tcp
```

### 3. View Logs

```bash
# All services
docker-compose logs -f

# Just Postgres
docker-compose logs -f postgres

# Just Redis
docker-compose logs -f redis
```

---

## Testing Database Connections

### Test PostgreSQL Connection

```bash
# Using psql (if installed)
psql -h localhost -U kisan -d kisan_ai
# Password: kisan_secure_dev_password

# Or using Docker
docker-compose exec postgres psql -U kisan -d kisan_ai
```

Once connected, test:
```sql
\dt  -- List tables
SELECT version();  -- Check PostgreSQL version
CREATE TABLE test (id SERIAL PRIMARY KEY, name TEXT);
SELECT * FROM test;
DROP TABLE test;
\q  -- Quit
```

### Test Redis Connection

```bash
# Using redis-cli (if installed)
redis-cli -h localhost -p 6379

# Or using Docker
docker-compose exec redis redis-cli
```

Once connected, test:
```
PING  -- Should return PONG
SET key "Hello"
GET key
DEL key
EXIT
```

### Test from Python

```python
import asyncio
import asyncpg
import redis

async def test_postgres():
    conn = await asyncpg.connect(
        'postgresql://kisan:kisan_secure_dev_password@localhost:5432/kisan_ai'
    )
    version = await conn.fetchval('SELECT version()')
    print(f"✅ Postgres: {version[:50]}...")
    await conn.close()

def test_redis():
    r = redis.Redis(host='localhost', port=6379, decode_responses=True)
    r.set('test', 'Hello')
    value = r.get('test')
    print(f"✅ Redis: {value}")
    r.delete('test')

# Run tests
asyncio.run(test_postgres())
test_redis()
```

---

## Database Migration (Alembic)

Once services are running, initialize the database schema:

```bash
# Run migrations
cd ~/projects/kisan-ai
alembic upgrade head

# Check migration status
alembic current
```

---

## Stopping Services

### Stop (data preserved)
```bash
docker-compose down
```

### Stop and delete volumes (data deleted)
```bash
docker-compose down -v
```

---

## Troubleshooting

### Services won't start
```bash
# Check logs
docker-compose logs

# Try removing and starting fresh
docker-compose down -v
docker-compose up -d
```

### Can't connect to PostgreSQL
```bash
# Verify service is healthy
docker-compose ps

# Check if port 5432 is available
netstat -an | grep 5432  # Windows: netstat -ano | findstr 5432
```

### Can't connect to Redis
```bash
# Verify Redis is running
docker-compose logs redis

# Check port 6379
netstat -an | grep 6379  # Windows: netstat -ano | findstr 6379
```

### Connection refused errors
- Wait 10-15 seconds for services to start (health checks need time)
- Check `.env` has correct credentials: `kisan_secure_dev_password`
- Verify ports are not already in use

---

## Configuration Files

- **docker-compose.yml** - Service definitions
- **.env** - Connection strings (loaded by app)
- **vendor-research/02-docker-compose.md** - Detailed design

---

## Security Notes (Development Only)

⚠️ These settings are for **local development only**:
- Default password: `kisan_secure_dev_password` (change in production!)
- No authentication for Redis (add in production)
- Port 5432/6379 exposed (firewall in production)

For production, use:
- Strong random passwords
- Redis AUTH configured
- Network isolation
- Cloud-managed databases (AWS RDS, Google Cloud SQL)

---

## Important: Celery Scheduler

The bot uses **Celery Beat** for scheduled tasks. Ensure Redis is healthy before starting Celery:

```bash
# Terminal 1: Celery Beat (scheduler)
celery -A src.scheduler.celery_app beat -l info

# Terminal 2: Celery Worker (executes tasks)
celery -A src.scheduler.celery_app worker -l info
```

**Scheduled Tasks**:
- **6:30 AM IST** — Daily price broadcast to all active farmers
- **1:00 AM IST** — Hard-delete farmers in 30-day erasure window (DPDPA compliance)

---

## Advanced: Accessing Database Directly

### View Farmers
```bash
docker-compose exec postgres psql -U kisan -d kisan_ai -c "SELECT id, phone, name, district, onboarding_state FROM farmers LIMIT 5;"
```

### View Conversations
```bash
docker-compose exec postgres psql -U kisan -d kisan_ai -c "SELECT id, farmer_id, direction, detected_intent, raw_message FROM conversations LIMIT 10;"
```

### View Consent Events (DPDPA Audit Trail)
```bash
docker-compose exec postgres psql -U kisan -d kisan_ai -c "SELECT farmer_id, event_type, created_at FROM consent_events ORDER BY created_at DESC LIMIT 20;"
```

### View Erasure Requests
```bash
docker-compose exec postgres psql -U kisan -d kisan_ai -c "SELECT id, phone, name, erasure_requested_at FROM farmers WHERE erasure_requested_at IS NOT NULL;"
```

---

## Production Considerations

For **Phase 2+** (June 2026 onward):

1. **Cloud Database**: Migrate to AWS RDS PostgreSQL
   - Managed backups, replication, auto-scaling
   - Command: `terraform apply` (AWS config in `infra/`)

2. **Cloud Cache**: Migrate to AWS ElastiCache Redis
   - High availability, automatic failover

3. **Celery on Kubernetes**: Scale workers horizontally
   - Deploy with ECS/EKS

4. **Monitoring**: Set up CloudWatch, Datadog, or New Relic
   - Monitor API latency, task execution, error rates

5. **Security**: Add VPC, security groups, SSL/TLS
   - Encrypt data in transit (TLS 1.3)
   - Encrypt data at rest (AWS KMS)

---

## Troubleshooting: Celery Issues

### Celery Worker doesn't start
```bash
# Check Redis connection
docker-compose exec redis redis-cli PING
# Should return: PONG

# Check Celery app
python -c "from src.scheduler.celery_app import app; print('✅ Celery app loaded')"
```

### Tasks not executing at scheduled time
```bash
# Check Celery Beat logs
celery -A src.scheduler.celery_app beat -l debug

# Verify task queue
docker-compose exec redis redis-cli
> KEYS celery*
> LRANGE celery 0 -1
```

### Broadcast task errors
```bash
# Check recent task results
docker-compose exec redis redis-cli
> HGETALL celery-task-meta-*

# Or view in PostgreSQL
# SELECT * FROM broadcast_log WHERE status = 'failed' LIMIT 10;
```

---

## What's Next?

**Phase 1 MVP**: All 11 modules complete (April 2026)
- ✅ Field testing with farmers
- ✅ DPDPA v2023 compliance
- ✅ 216 tests passing

**Phase 2** (June–July 2026):
- Voice message support
- Photo-based pest diagnosis
- Weather integration
- Government schemes & MSP alerts
- Price alerts

---

Happy developing! 🚀
