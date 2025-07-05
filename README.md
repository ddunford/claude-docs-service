# Document Storage Microservice

A comprehensive document storage microservice built with FastAPI, gRPC, and modern cloud-native technologies. Supports document upload, parsing, versioning, digital signing, virus scanning, and secure storage with pluggable backends.

## 🚀 Features

- **Dual API Support**: Both REST (FastAPI) and gRPC APIs
- **Multi-Storage Backend**: S3, MinIO, GCS, Azure Blob (pluggable architecture)
- **Virus Scanning**: Integrated ClamAV antivirus scanning
- **Document Versioning**: Complete version history tracking
- **Multi-Tenancy**: Tenant-aware document isolation
- **Event-Driven**: RabbitMQ for async event processing
- **Observability**: OpenTelemetry tracing, Prometheus metrics, structured logging
- **Authentication**: OAuth2 JWT with scope-based permissions
- **Database**: PostgreSQL for metadata, Redis for caching and sessions
- **Cloud-Ready**: Docker, Kubernetes, and cloud-native deployment

## 🏗️ Architecture

```
┌─────────────────┐    ┌─────────────────┐
│   REST API      │    │   gRPC API      │
│   (FastAPI)     │    │   (Python)      │
└─────────┬───────┘    └─────────┬───────┘
          │                      │
          └──────────┬───────────┘
                     │
         ┌───────────▼───────────┐
         │   Document Service    │
         │   Business Logic      │
         └───────────┬───────────┘
                     │
     ┌───────────────┼───────────────┐
     │               │               │
┌────▼────┐    ┌────▼────┐    ┌────▼────┐
│Storage  │    │Database │    │  Cache  │
│S3/MinIO │    │Postgres │    │  Redis  │
└─────────┘    └─────────┘    └─────────┘
     │               │               │
┌────▼────┐    ┌────▼────┐    ┌────▼────┐
│Virus    │    │Events   │    │Metrics  │
│ClamAV   │    │RabbitMQ │    │Prometheus│
└─────────┘    └─────────┘    └─────────┘
```

## 🚀 Quick Start

### Prerequisites

- Docker and Docker Compose
- Python 3.11+ (for local development)
- Make (optional, for convenient commands)

### Development Setup

1. **Clone and setup environment:**
   ```bash
   git clone <repository-url>
   cd documents-service
   make dev-setup
   ```

2. **Start development services:**
   ```bash
   make dev
   ```

3. **Run the application:**
   ```bash
   make run
   ```

4. **Access the services:**
   - REST API: http://localhost:8000
   - gRPC API: localhost:50051
   - API Documentation: http://localhost:8000/docs
   - Metrics: http://localhost:8001/metrics

### Using Docker Compose

```bash
# Start all services
docker compose up --build

# Start in background
docker compose up -d --build

# View logs
docker compose logs -f app

# Stop services
docker compose down
```

## 📚 API Documentation

### REST API Endpoints

- `POST /api/v1/documents/upload` - Upload a document
- `GET /api/v1/documents/{id}` - Get document metadata
- `DELETE /api/v1/documents/{id}` - Delete document
- `GET /api/v1/documents` - List documents
- `POST /api/v1/documents/{id}/scan` - Trigger virus scan
- `GET /api/v1/health` - Health check

### gRPC Services

- `UploadDocument` - Upload a document
- `GetDocument` - Retrieve document
- `DeleteDocument` - Delete document
- `ListDocuments` - List documents
- `ScanDocument` - Trigger virus scan

## 🧪 Testing

```bash
# Run all tests
make test

# Run specific test types
pytest tests/unit/
pytest tests/integration/

# Run with coverage
pytest --cov=app --cov-report=html
```

## 🔧 Configuration

Configuration is managed through environment variables. See `.env.example` for all available options.

### Key Environment Variables

```bash
# Database
DATABASE_URL=postgresql+asyncpg://user:pass@localhost/db
REDIS_URL=redis://localhost:6379/0

# Storage
STORAGE_BACKEND=minio  # s3, minio, gcs
S3_ENDPOINT_URL=http://localhost:9000
S3_ACCESS_KEY_ID=minioadmin
S3_SECRET_ACCESS_KEY=minioadmin

# Security
JWT_SECRET_KEY=your-secret-key
VIRUS_SCAN_ENABLED=true
CLAMAV_HOST=localhost

# Messaging
RABBITMQ_URL=amqp://guest:guest@localhost:5672/
```

## 🛠️ Development

### Code Quality

```bash
# Format code
make format

# Run linting
make lint

# Type checking
mypy app/
```

### Database Migrations

```bash
# Create migration
alembic revision --autogenerate -m "Description"

# Apply migrations
make migrate
```

### Generate Protocol Buffers

```bash
make proto
```

## 📊 Monitoring & Observability

- **Metrics**: Prometheus metrics at `:8001/metrics`
- **Tracing**: Jaeger UI at `http://localhost:16686`
- **Logs**: Structured JSON logging with correlation IDs
- **Health Checks**: `/api/v1/health` endpoint

### Available Metrics

- `doc_upload_count` - Total document uploads
- `doc_scan_failures` - Virus scan failures
- `doc_size_bytes` - Document size distribution

## 🔒 Security

- OAuth2 JWT authentication
- Scope-based authorization (`doc.read`, `doc.write`, `doc.admin`)
- Virus scanning with ClamAV
- Secure storage with encryption at rest
- Audit logging for all operations

## 🚀 Deployment

### Docker

```bash
# Build production image
docker build -t document-service .

# Run with production settings
docker run -p 8000:8000 --env-file .env document-service
```

### Kubernetes

See `k8s/` directory for Kubernetes deployment manifests.

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Run the full test suite
6. Submit a pull request

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🔗 Related Services

- `user-service` - User management and authentication
- `llm-service` - Document processing and AI analysis
- `workflow-service` - Document workflow automation