// K6 Load Test for Document Service
import http from 'k6/http';
import { check, sleep } from 'k6';
import { Rate } from 'k6/metrics';

// Custom metrics
const errorRate = new Rate('errors');

// Test configuration
export const options = {
  stages: [
    { duration: '30s', target: 5 },   // Ramp up to 5 users
    { duration: '1m', target: 10 },   // Stay at 10 users
    { duration: '30s', target: 20 },  // Ramp up to 20 users
    { duration: '1m', target: 20 },   // Stay at 20 users
    { duration: '30s', target: 0 },   // Ramp down to 0 users
  ],
  thresholds: {
    http_req_duration: ['p(95)<1000'], // 95% of requests should be below 1s
    http_req_failed: ['rate<0.1'],     // Error rate should be below 10%
    errors: ['rate<0.1'],              // Custom error rate should be below 10%
  },
};

// Base URL configuration
const BASE_URL = __ENV.BASE_URL || 'http://localhost:8000';

// Test data
const testDocuments = [
  { title: 'Test Document 1', content: 'This is test content 1' },
  { title: 'Test Document 2', content: 'This is test content 2' },
  { title: 'Test Document 3', content: 'This is test content 3' },
];

// Authentication token (mock)
const authToken = 'Bearer test-token';

// Helper function to create headers
function getHeaders() {
  return {
    'Content-Type': 'application/json',
    'Authorization': authToken,
  };
}

// Test scenarios
export default function() {
  // Health check
  let response = http.get(`${BASE_URL}/api/v1/health`);
  check(response, {
    'health check status is 200': (r) => r.status === 200,
    'health check response time < 500ms': (r) => r.timings.duration < 500,
  }) || errorRate.add(1);

  sleep(1);

  // List documents
  response = http.get(`${BASE_URL}/api/v1/documents`, {
    headers: getHeaders(),
  });
  check(response, {
    'list documents status is 200': (r) => r.status === 200,
    'list documents response time < 1000ms': (r) => r.timings.duration < 1000,
  }) || errorRate.add(1);

  sleep(1);

  // Create a document
  const randomDoc = testDocuments[Math.floor(Math.random() * testDocuments.length)];
  response = http.post(`${BASE_URL}/api/v1/documents`, JSON.stringify(randomDoc), {
    headers: getHeaders(),
  });
  check(response, {
    'create document status is 201': (r) => r.status === 201,
    'create document response time < 2000ms': (r) => r.timings.duration < 2000,
  }) || errorRate.add(1);

  let documentId;
  if (response.status === 201) {
    const body = JSON.parse(response.body);
    documentId = body.id;
  }

  sleep(1);

  // Get document by ID (if created successfully)
  if (documentId) {
    response = http.get(`${BASE_URL}/api/v1/documents/${documentId}`, {
      headers: getHeaders(),
    });
    check(response, {
      'get document status is 200': (r) => r.status === 200,
      'get document response time < 1000ms': (r) => r.timings.duration < 1000,
    }) || errorRate.add(1);

    sleep(1);

    // Update document
    const updateData = {
      title: randomDoc.title + ' (Updated)',
      content: randomDoc.content + ' (Updated)',
    };
    response = http.put(`${BASE_URL}/api/v1/documents/${documentId}`, JSON.stringify(updateData), {
      headers: getHeaders(),
    });
    check(response, {
      'update document status is 200': (r) => r.status === 200,
      'update document response time < 2000ms': (r) => r.timings.duration < 2000,
    }) || errorRate.add(1);

    sleep(1);

    // Delete document
    response = http.del(`${BASE_URL}/api/v1/documents/${documentId}`, null, {
      headers: getHeaders(),
    });
    check(response, {
      'delete document status is 204': (r) => r.status === 204,
      'delete document response time < 1000ms': (r) => r.timings.duration < 1000,
    }) || errorRate.add(1);
  }

  sleep(2);
}

// Setup function (runs once before all VUs)
export function setup() {
  console.log('Starting load test...');
  console.log(`Base URL: ${BASE_URL}`);
  console.log(`Test configuration: ${JSON.stringify(options)}`);
}

// Teardown function (runs once after all VUs)
export function teardown() {
  console.log('Load test completed!');
}