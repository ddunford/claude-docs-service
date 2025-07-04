#!/bin/bash

# Script to generate Python gRPC code from protobuf definitions

set -e

echo "Generating Python gRPC code from protobuf definitions..."

# Ensure we're in the project root
cd "$(dirname "$0")/.."

# Generate Python files from protobuf definitions
python -m grpc_tools.protoc \
    --proto_path=proto \
    --python_out=. \
    --grpc_python_out=. \
    proto/docs/v1/document.proto

echo "Generated Python gRPC code successfully!"
echo "Files generated:"
echo "- docs/v1/document_pb2.py"
echo "- docs/v1/document_pb2_grpc.py"

# Create __init__.py files in generated directories
mkdir -p docs/v1
touch docs/__init__.py
touch docs/v1/__init__.py

echo "Proto generation complete!"