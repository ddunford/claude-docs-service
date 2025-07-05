# Document Service Makefile

.PHONY: help install dev test lint format clean build run stop logs migrate init-db proto

# Default target
help:
	@echo "Document Service - Available commands:"
	@echo "  install     - Install dependencies"
	@echo "  dev         - Start development environment"
	@echo "  test        - Run tests"
	@echo "  lint        - Run linting"
	@echo "  format      - Format code"
	@echo "  clean       - Clean up containers and volumes"
	@echo "  build       - Build Docker image"
	@echo "  run         - Run application"
	@echo "  stop        - Stop application"
	@echo "  logs        - View application logs"
	@echo "  migrate     - Run database migrations"
	@echo "  init-db     - Initialize database"
	@echo "  proto       - Generate protobuf files"

# Install dependencies
install:
	pip install -e .
	pip install -e ".[dev]"

# Start development environment
dev:
	docker compose up -d postgres redis minio rabbitmq clamav jaeger
	sleep 10
	docker compose up minio-init
	@echo "Development services started. Run 'make run' to start the application."

# Run tests
test:
	pytest tests/ -v --cov=app --cov-report=html --cov-report=term-missing

# Run linting
lint:
	ruff check app tests
	mypy app

# Format code
format:
	black app tests
	ruff check app tests --fix

# Clean up
clean:
	docker compose down -v
	docker system prune -f
	rm -rf .pytest_cache
	rm -rf htmlcov
	rm -rf .coverage
	rm -rf .mypy_cache
	rm -rf .ruff_cache

# Build Docker image
build:
	docker compose build

# Run application
run:
	python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Stop application
stop:
	docker compose stop

# View logs
logs:
	docker compose logs -f app

# Run database migrations
migrate:
	alembic upgrade head

# Initialize database
init-db:
	alembic revision --autogenerate -m "Initial migration"
	alembic upgrade head

# Generate protobuf files
proto:
	./scripts/generate_protos.sh

# Development workflow
dev-setup: install dev proto init-db
	@echo "Development environment setup complete!"

# Run full CI pipeline
ci: lint test
	@echo "CI pipeline completed successfully!"

# Docker development
docker-dev:
	docker compose up --build

# Docker production
docker-prod:
	docker compose -f docker-compose.yml -f docker-compose.prod.yml up --build

# Health check
health:
	curl -f http://localhost:8000/api/v1/health || exit 1

# Monitor
monitor:
	@echo "Prometheus: http://localhost:9090"
	@echo "Grafana: http://localhost:3000 (admin/admin)"
	@echo "Jaeger: http://localhost:16686"
	@echo "RabbitMQ: http://localhost:15672 (guest/guest)"
	@echo "MinIO: http://localhost:9001 (minioadmin/minioadmin)"