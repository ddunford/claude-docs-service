#!/bin/bash

# Infrastructure Validation Script
# This script validates the infrastructure setup for the document service

set -e

echo "🔍 Validating Document Service Infrastructure..."
echo "================================================"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print status
print_status() {
    if [ $1 -eq 0 ]; then
        echo -e "${GREEN}✅ $2${NC}"
    else
        echo -e "${RED}❌ $2${NC}"
    fi
}

# Function to print warning
print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

# Function to print info
print_info() {
    echo -e "ℹ️  $1"
}

# Validation functions
validate_files() {
    echo "📁 Validating required files..."
    
    files=(
        "Dockerfile"
        "docker-compose.yml"
        "docker-compose.prod.yml"
        "Makefile"
        "pyproject.toml"
        ".env"
        ".env.prod.template"
        ".pre-commit-config.yaml"
        ".github/workflows/ci.yml"
        ".github/workflows/deploy.yml"
        "monitoring/prometheus.yml"
        "monitoring/prometheus.prod.yml"
        "monitoring/grafana/provisioning/datasources/datasources.yml"
        "monitoring/grafana/provisioning/dashboards/dashboards.yml"
        "nginx/nginx.conf"
        "scripts/init_db.sql"
        "scripts/generate_protos.sh"
        "tests/performance/load_test.js"
    )
    
    missing_files=()
    
    for file in "${files[@]}"; do
        if [ -f "$file" ]; then
            print_status 0 "$file exists"
        else
            print_status 1 "$file is missing"
            missing_files+=("$file")
        fi
    done
    
    if [ ${#missing_files[@]} -eq 0 ]; then
        print_info "All required files are present"
    else
        print_warning "Missing files: ${missing_files[*]}"
        return 1
    fi
}

validate_docker_compose() {
    echo "🐳 Validating Docker Compose configuration..."
    
    # Check if docker is available
    if ! command -v docker &> /dev/null; then
        print_status 1 "Docker is not installed"
        return 1
    fi
    
    # Validate development docker-compose
    if docker compose config > /dev/null 2>&1; then
        print_status 0 "Development docker-compose.yml is valid"
    else
        print_status 1 "Development docker-compose.yml is invalid"
        return 1
    fi
    
    # Validate production docker-compose
    if docker compose -f docker-compose.yml -f docker-compose.prod.yml config > /dev/null 2>&1; then
        print_status 0 "Production docker-compose configuration is valid"
    else
        print_status 1 "Production docker-compose configuration is invalid"
        return 1
    fi
}

validate_makefile() {
    echo "🔧 Validating Makefile..."
    
    # Check if make is available
    if ! command -v make &> /dev/null; then
        print_status 1 "Make is not installed"
        return 1
    fi
    
    # Check required targets
    required_targets=("help" "install" "dev" "test" "lint" "format" "clean" "build" "run")
    
    for target in "${required_targets[@]}"; do
        if make -n $target > /dev/null 2>&1; then
            print_status 0 "Makefile target '$target' exists"
        else
            print_status 1 "Makefile target '$target' is missing"
            return 1
        fi
    done
}

validate_python_config() {
    echo "🐍 Validating Python configuration..."
    
    # Check pyproject.toml
    if [ -f "pyproject.toml" ]; then
        print_status 0 "pyproject.toml exists"
        
        # Check for required sections
        required_sections=("build-system" "project" "project.optional-dependencies" "tool.pytest.ini_options" "tool.black" "tool.ruff" "tool.mypy")
        
        for section in "${required_sections[@]}"; do
            if grep -q "\\[$section\\]" pyproject.toml; then
                print_status 0 "pyproject.toml has [$section] section"
            else
                print_status 1 "pyproject.toml missing [$section] section"
            fi
        done
    else
        print_status 1 "pyproject.toml is missing"
        return 1
    fi
}

validate_env_files() {
    echo "🔐 Validating environment files..."
    
    # Check .env file
    if [ -f ".env" ]; then
        print_status 0 ".env file exists"
        
        # Check for required variables
        required_vars=("DEBUG" "DATABASE_URL" "REDIS_URL" "JWT_SECRET_KEY" "S3_BUCKET_NAME")
        
        for var in "${required_vars[@]}"; do
            if grep -q "^$var=" .env; then
                print_status 0 ".env has $var variable"
            else
                print_status 1 ".env missing $var variable"
            fi
        done
    else
        print_status 1 ".env file is missing"
        return 1
    fi
    
    # Check .env.prod.template
    if [ -f ".env.prod.template" ]; then
        print_status 0 ".env.prod.template exists"
    else
        print_status 1 ".env.prod.template is missing"
        return 1
    fi
}

validate_monitoring() {
    echo "📊 Validating monitoring configuration..."
    
    # Check Prometheus config
    if [ -f "monitoring/prometheus.yml" ]; then
        print_status 0 "Prometheus configuration exists"
        
        # Check for required sections
        if grep -q "global:" monitoring/prometheus.yml; then
            print_status 0 "Prometheus config has global section"
        else
            print_status 1 "Prometheus config missing global section"
        fi
        
        if grep -q "scrape_configs:" monitoring/prometheus.yml; then
            print_status 0 "Prometheus config has scrape_configs section"
        else
            print_status 1 "Prometheus config missing scrape_configs section"
        fi
    else
        print_status 1 "Prometheus configuration is missing"
        return 1
    fi
    
    # Check Grafana config
    if [ -f "monitoring/grafana/provisioning/datasources/datasources.yml" ]; then
        print_status 0 "Grafana datasources configuration exists"
    else
        print_status 1 "Grafana datasources configuration is missing"
        return 1
    fi
    
    if [ -f "monitoring/grafana/provisioning/dashboards/dashboards.yml" ]; then
        print_status 0 "Grafana dashboards configuration exists"
    else
        print_status 1 "Grafana dashboards configuration is missing"
        return 1
    fi
}

validate_ci_cd() {
    echo "🚀 Validating CI/CD configuration..."
    
    # Check GitHub Actions workflows
    if [ -f ".github/workflows/ci.yml" ]; then
        print_status 0 "CI workflow exists"
        
        # Check for required jobs
        required_jobs=("lint" "unit-tests" "integration-tests" "docker-build")
        
        for job in "${required_jobs[@]}"; do
            if grep -q "  $job:" .github/workflows/ci.yml; then
                print_status 0 "CI workflow has $job job"
            else
                print_status 1 "CI workflow missing $job job"
            fi
        done
    else
        print_status 1 "CI workflow is missing"
        return 1
    fi
    
    if [ -f ".github/workflows/deploy.yml" ]; then
        print_status 0 "Deploy workflow exists"
    else
        print_status 1 "Deploy workflow is missing"
        return 1
    fi
}

validate_security() {
    echo "🔒 Validating security configuration..."
    
    # Check pre-commit hooks
    if [ -f ".pre-commit-config.yaml" ]; then
        print_status 0 "Pre-commit configuration exists"
        
        # Check for security hooks
        if grep -q "bandit" .pre-commit-config.yaml; then
            print_status 0 "Bandit security scanning is configured"
        else
            print_status 1 "Bandit security scanning is not configured"
        fi
    else
        print_status 1 "Pre-commit configuration is missing"
        return 1
    fi
    
    # Check for secrets in .env (basic check)
    if grep -q "CHANGE_ME\|password\|secret" .env; then
        print_warning "Found default/placeholder values in .env file"
    else
        print_status 0 "No obvious placeholder values in .env file"
    fi
}

validate_scripts() {
    echo "📜 Validating scripts..."
    
    # Check script files
    scripts=("scripts/init_db.sql" "scripts/generate_protos.sh")
    
    for script in "${scripts[@]}"; do
        if [ -f "$script" ]; then
            print_status 0 "$script exists"
            
            # Check if shell scripts are executable
            if [[ "$script" == *.sh ]]; then
                if [ -x "$script" ]; then
                    print_status 0 "$script is executable"
                else
                    print_warning "$script is not executable"
                    chmod +x "$script"
                    print_info "Made $script executable"
                fi
            fi
        else
            print_status 1 "$script is missing"
        fi
    done
}

# Main validation
main() {
    echo "Starting infrastructure validation..."
    echo
    
    validation_failed=0
    
    validate_files || validation_failed=1
    echo
    
    validate_docker_compose || validation_failed=1
    echo
    
    validate_makefile || validation_failed=1
    echo
    
    validate_python_config || validation_failed=1
    echo
    
    validate_env_files || validation_failed=1
    echo
    
    validate_monitoring || validation_failed=1
    echo
    
    validate_ci_cd || validation_failed=1
    echo
    
    validate_security || validation_failed=1
    echo
    
    validate_scripts || validation_failed=1
    echo
    
    echo "================================================"
    if [ $validation_failed -eq 0 ]; then
        echo -e "${GREEN}🎉 Infrastructure validation completed successfully!${NC}"
        echo
        echo "Next steps:"
        echo "1. Review and update .env file with appropriate values"
        echo "2. Copy .env.prod.template to .env.prod and set production values"
        echo "3. Generate SSL certificates for nginx (nginx/ssl/)"
        echo "4. Run 'make dev' to start development environment"
        echo "5. Run 'make test' to run tests"
        echo "6. Setup pre-commit hooks with 'pre-commit install'"
        exit 0
    else
        echo -e "${RED}❌ Infrastructure validation failed!${NC}"
        echo "Please fix the issues above and run the validation again."
        exit 1
    fi
}

# Run main function
main "$@"