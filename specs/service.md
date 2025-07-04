# 📂 Document Service Specification

## 1. Service Name

`document-service`

---

## 2. Purpose

Manages document upload, parsing, versioning, digital signing, and secure storage with support for pluggable storage backends.

---

## 3. Owner

Core Platform Team

---

## 4. Tech Stack

* **Language:** Python
* **Framework:** FastAPI (gRPC + REST gateway)
* **Database:** Postgres for metadata, Redis for transient states
* **Messaging:** RabbitMQ (event-driven coordination)
* **Container:** Docker
* **Runtime:** Kubernetes
* **Storage Providers:** MinIO (dev), S3 (prod), future: Azure Blob, GCS
* **Virus Scanning:** ClamAV (integrated via sidecar)

---

## 5. APIs

### 5.1 gRPC Endpoints

| Method           | Request Message     | Response Message       | Description                             |
| ---------------- | ------------------- | ---------------------- | --------------------------------------- |
| `UploadDocument` | `UploadRequest`     | `UploadResponse`       | Uploads a document to storage           |
| `GetDocument`    | `DocumentIdRequest` | `DocumentResponse`     | Fetch document metadata and content     |
| `DeleteDocument` | `DocumentIdRequest` | `EmptyResponse`        | Soft deletes document (archival policy) |
| `ScanDocument`   | `DocumentIdRequest` | `ScanResult`           | Triggers AV scan, returns status        |
| `ListDocuments`  | `ListRequest`       | `DocumentListResponse` | List documents by owner, tags, etc.     |

---

## 6. Auth & Permissions

* **Auth type:** OAuth2 JWT (via gateway)
* Scopes:

  * `doc.read`: List/download documents
  * `doc.write`: Upload/delete documents
  * `doc.admin`: Trigger scans, manage templates

---

## 7. Data Contracts

* **Input Schemas:** `UploadRequest`, `DocumentMetadata`, `StorageLocation`
* **Output Schemas:** `DocumentResponse`, `ScanResult`, `VersionHistory`
* Versioned `.proto` definitions under `/proto/docs/v1/`

---

## 8. Dependencies

* **Upstream:** `user-service`, `llm-service`, `workflow-service`
* **Downstream:** `frontend-service`, `application-service`, `claude-service`
* **External APIs:** AWS S3, MinIO, ClamAV REST socket, optionally Docusign

---

## 9. Storage & State

* **Postgres:**

  * Document metadata
  * Upload audit trails
  * Version history
* **Redis:**

  * Upload session tracking
  * Virus scan jobs
* **Storage:**

  * Bucketed per-tenant file storage (S3 API compliant)

---

## 10. Events & Messaging

* **Publishes:**

  * `document.uploaded`
  * `document.scanned`
  * `document.deleted`
* **Consumes:**

  * `user.created`
  * `application.submitted`

---

## 11. Configuration

* `STORAGE_BACKEND` = s3|minio|gcs
* `MAX_FILE_SIZE_MB` = 20
* `VIRUS_SCAN_ENABLED=true`
* Secrets (e.g. credentials) via Vault + Kubernetes secrets

---

## 12. Observability

* **Logs:** Structured JSON (doc ID, tenant, trace ID)
* **Metrics:**

  * `doc_upload_count`
  * `doc_scan_failures`
  * `doc_size_bytes`
* **Tracing:** OpenTelemetry w/ Jaeger

---

## 13. Scaling & Limits

* QPS: 100 sustained (peak 500)
* Upload size: up to 20MB (soft limit)
* Files per tenant: 100,000+ supported
* Rate limits via gateway (per token/tenant)

---

## 14. CI/CD

* GitHub Actions pipeline:

  * `pytest` for all handlers
  * Contract tests (`grpcurl`, `buf`) against proto
  * AV test mocks
* Deployment:

  * Canary + rolling updates
  * Blue/green for storage backend changes

---

## 15. SLA/SLOs

* **Uptime:** 99.95%
* **Upload latency:** <1s (p95)
* **Scan turnaround:** <5s
* **Error rate threshold:** <0.5%

---

## 16. Notes / TODOs

* [ ] Support resumable uploads via gRPC streaming
* [ ] Add OCR pipeline for scanned PDF enrichment
* [ ] Optional: async AV scan decoupled from upload

---

## Unit Testing Requirements

* 100% unit test coverage on:

  * Metadata saving logic
  * File upload handlers (mocked S3/MinIO)
  * Virus scan response handler
  * gRPC contract validation (via `grpcio-testing`)
* Use `pytest` + `moto` (S3 mock) + `testcontainers` (for Redis + Postgres)
* CI checks for:

  * AV scanner not skipped
  * All gRPC responses tested for error + happy path
  * Contract compliance against `.proto`

---

