#!/bin/bash
# ============================================
# HPE GreenLake Sync - Interactive Setup
# ============================================
# This script:
#   1. Prompts for GreenLake API credentials
#   2. Prompts for PostgreSQL settings (with defaults)
#   3. Creates .env file
#   4. Builds and starts Docker containers
#
# Usage:
#   chmod +x setup.sh
#   ./setup.sh

set -e  # Exit on error

# ============================================
# Colors for pretty output
# ============================================
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color
BOLD='\033[1m'

# ============================================
# Helper Functions
# ============================================
print_header() {
    echo ""
    echo -e "${BLUE}════════════════════════════════════════════════════════════${NC}"
    echo -e "${BOLD}${CYAN}  $1${NC}"
    echo -e "${BLUE}════════════════════════════════════════════════════════════${NC}"
    echo ""
}

print_step() {
    echo -e "${GREEN}▶${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}⚠${NC}  $1"
}

print_error() {
    echo -e "${RED}✖${NC}  $1"
}

print_success() {
    echo -e "${GREEN}✔${NC}  $1"
}

# Prompt with default value
prompt_with_default() {
    local prompt="$1"
    local default="$2"
    local var_name="$3"
    local is_secret="$4"
    
    if [ -n "$default" ]; then
        echo -ne "${CYAN}$prompt${NC} [${YELLOW}$default${NC}]: "
    else
        echo -ne "${CYAN}$prompt${NC}: "
    fi
    
    if [ "$is_secret" = "true" ]; then
        read -s value
        echo ""  # New line after hidden input
    else
        read value
    fi
    
    # Use default if empty
    if [ -z "$value" ]; then
        value="$default"
    fi
    
    eval "$var_name='$value'"
}

# Prompt for required value (no default)
prompt_required() {
    local prompt="$1"
    local var_name="$2"
    local is_secret="$3"
    local value=""
    
    while [ -z "$value" ]; do
        echo -ne "${CYAN}$prompt${NC}: "
        
        if [ "$is_secret" = "true" ]; then
            read -s value
            echo ""
        else
            read value
        fi
        
        if [ -z "$value" ]; then
            print_error "This field is required. Please enter a value."
        fi
    done
    
    eval "$var_name='$value'"
}

# ============================================
# Main Script
# ============================================
clear

print_header "HPE GreenLake Sync - Setup Wizard"

echo "This wizard will help you configure and start the GreenLake sync service."
echo "You'll need your HPE GreenLake API credentials ready."
echo ""

# Check for Docker
if ! command -v docker &> /dev/null; then
    print_error "Docker is not installed. Please install Docker first."
    echo "  https://docs.docker.com/get-docker/"
    exit 1
fi

if ! command -v docker compose &> /dev/null; then
    print_error "Docker Compose is not installed. Please install Docker Compose first."
    exit 1
fi

print_success "Docker found: $(docker --version)"
echo ""

# ============================================
# GreenLake API Credentials (Required)
# ============================================
print_header "Step 1: GreenLake API Credentials"

echo "Enter your HPE GreenLake Platform API credentials."
echo "You can get these from the HPE GreenLake console."
echo ""

prompt_required "GLP Client ID" GLP_CLIENT_ID
prompt_required "GLP Client Secret" GLP_CLIENT_SECRET "true"
prompt_with_default "GLP Token URL" "https://sso.common.cloud.hpe.com/as/token.oauth2" GLP_TOKEN_URL
prompt_with_default "GLP Base URL" "https://global.api.greenlake.hpe.com" GLP_BASE_URL

echo ""
print_success "GreenLake credentials configured"

# ============================================
# PostgreSQL Settings (with defaults)
# ============================================
print_header "Step 2: PostgreSQL Database Settings"

echo "Configure the PostgreSQL database (press Enter for defaults)."
echo ""

prompt_with_default "Database User" "glp" POSTGRES_USER
prompt_with_default "Database Password" "glp_secret_$(openssl rand -hex 4)" POSTGRES_PASSWORD "true"
prompt_with_default "Database Name" "greenlake" POSTGRES_DB

echo ""
print_success "Database settings configured"

# ============================================
# Scheduler Settings (with defaults)
# ============================================
print_header "Step 3: Sync Scheduler Settings"

echo "Configure how often to sync (press Enter for defaults)."
echo ""

prompt_with_default "Sync interval (minutes)" "60" SYNC_INTERVAL_MINUTES
prompt_with_default "Sync devices? (true/false)" "true" SYNC_DEVICES
prompt_with_default "Sync subscriptions? (true/false)" "true" SYNC_SUBSCRIPTIONS
prompt_with_default "Sync on startup? (true/false)" "true" SYNC_ON_STARTUP

echo ""
print_success "Scheduler settings configured"

# ============================================
# API Security Settings
# ============================================
print_header "Step 4: API Security Configuration"

echo "Configure API authentication for the dashboard and assignment APIs."
echo ""
echo "  1) Development mode - No authentication required"
echo "  2) Production mode - API key required (auto-generated)"
echo ""

echo -ne "${CYAN}Select mode (1-2)${NC} [${YELLOW}1${NC}]: "
read security_mode

# Default to development
if [ -z "$security_mode" ]; then
    security_mode="1"
fi

DISABLE_AUTH="false"
API_KEY=""

case $security_mode in
    1)
        DISABLE_AUTH="true"
        REQUIRE_AUTH="false"
        JWT_SECRET=""
        print_success "Development mode: Authentication disabled"
        ;;
    2|*)
        DISABLE_AUTH="false"
        REQUIRE_AUTH="true"
        API_KEY=$(openssl rand -base64 32 | tr -d '/+=' | head -c 43)
        JWT_SECRET=$(openssl rand -base64 48 | tr -d '/+=' | head -c 64)
        echo ""
        print_success "Production mode: Secrets generated"
        echo -e "  ${YELLOW}API Key:    $API_KEY${NC}"
        echo -e "  ${YELLOW}JWT Secret: ${JWT_SECRET:0:16}...${NC}"
        echo ""
        echo -e "  ${CYAN}API Key: Use in X-API-Key header for dashboard/assignment APIs${NC}"
        echo -e "  ${CYAN}JWT Secret: Used internally for agent chatbot authentication${NC}"
        ;;
esac

echo ""

# ============================================
# AI Chatbot Settings (Optional)
# ============================================
print_header "Step 5: AI Chatbot Configuration"

echo "The AI chatbot can use different LLM providers."
echo "Select your preferred provider (or skip to configure later)."
echo ""
echo "  1) Anthropic (Claude) - Recommended"
echo "  2) OpenAI (GPT-4)"
echo "  3) Ollama (Local, no API key needed)"
echo "  4) Skip for now"
echo ""

echo -ne "${CYAN}Select LLM provider (1-4)${NC} [${YELLOW}4${NC}]: "
read llm_choice

# Default to skip
if [ -z "$llm_choice" ]; then
    llm_choice="4"
fi

LLM_PROVIDER=""
LLM_API_KEY=""
LLM_MODEL=""
EMBEDDING_MODEL=""

case $llm_choice in
    1)
        LLM_PROVIDER="anthropic"
        echo ""
        prompt_required "Anthropic API Key" LLM_API_KEY "true"
        prompt_with_default "Claude Model" "claude-sonnet-4-5-20250929" LLM_MODEL
        echo ""
        echo -e "${YELLOW}Note: Anthropic doesn't provide embeddings. Using OpenAI for embeddings.${NC}"
        echo -ne "${CYAN}OpenAI API Key for embeddings (optional, press Enter to skip)${NC}: "
        read -s OPENAI_API_KEY
        echo ""
        if [ -n "$OPENAI_API_KEY" ]; then
            EMBEDDING_MODEL="text-embedding-3-large"
        fi
        print_success "Anthropic (Claude) configured"
        ;;
    2)
        LLM_PROVIDER="openai"
        echo ""
        prompt_required "OpenAI API Key" LLM_API_KEY "true"
        prompt_with_default "GPT Model" "gpt-5-nano-2025-08-07" LLM_MODEL
        EMBEDDING_MODEL="text-embedding-3-large"
        print_success "OpenAI (GPT) configured"
        ;;
    3)
        LLM_PROVIDER="ollama"
        echo ""
        OLLAMA_BASE_URL="http://localhost:11434"
        prompt_with_default "Ollama Model" "qwen3:4b" LLM_MODEL
        echo -e "${YELLOW}Note: Ollama URL automatically set to $OLLAMA_BASE_URL${NC}"
        print_success "Ollama configured (run: ollama run $LLM_MODEL)"
        ;;
    4|*)
        echo ""
        print_warning "Skipping LLM configuration. You can add it to .env later."
        ;;
esac

echo ""

# ============================================
# Confirm Settings
# ============================================
print_header "Step 6: Confirm Configuration"

echo -e "${BOLD}GreenLake API:${NC}"
echo "  Client ID:     ${GLP_CLIENT_ID:0:8}..."
echo "  Client Secret: ********"
echo "  Token URL:     $GLP_TOKEN_URL"
echo "  Base URL:      $GLP_BASE_URL"
echo ""
echo -e "${BOLD}PostgreSQL:${NC}"
echo "  User:          $POSTGRES_USER"
echo "  Password:      ********"
echo "  Database:      $POSTGRES_DB"
echo ""
echo -e "${BOLD}Scheduler:${NC}"
echo "  Interval:      Every $SYNC_INTERVAL_MINUTES minutes"
echo "  Devices:       $SYNC_DEVICES"
echo "  Subscriptions: $SYNC_SUBSCRIPTIONS"
echo "  On Startup:    $SYNC_ON_STARTUP"
echo ""
echo -e "${BOLD}API Security:${NC}"
if [ "$DISABLE_AUTH" = "true" ]; then
    echo "  Mode:          Development (auth disabled)"
else
    echo "  Mode:          Production"
    echo "  API Key:       ${API_KEY:0:8}..."
    echo "  JWT Secret:    ${JWT_SECRET:0:8}..."
fi
echo ""
echo -e "${BOLD}AI Chatbot:${NC}"
if [ -n "$LLM_PROVIDER" ]; then
    echo "  Provider:      $LLM_PROVIDER"
    echo "  Model:         $LLM_MODEL"
    echo "  API Key:       ********"
    if [ -n "$EMBEDDING_MODEL" ]; then
        echo "  Embeddings:    $EMBEDDING_MODEL"
    fi
else
    echo "  Provider:      Not configured"
fi
echo ""

echo -ne "${YELLOW}Proceed with these settings? (y/n)${NC}: "
read confirm

if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
    print_warning "Setup cancelled. Run ./setup.sh again to restart."
    exit 0
fi

# ============================================
# Create .env File
# ============================================
print_header "Step 7: Creating Configuration"

print_step "Writing .env file..."

cat > .env << EOF
# ============================================
# HPE GreenLake Sync - Configuration
# Generated by setup.sh on $(date)
# ============================================

# GreenLake API Credentials
GLP_CLIENT_ID=$GLP_CLIENT_ID
GLP_CLIENT_SECRET=$GLP_CLIENT_SECRET
GLP_TOKEN_URL=$GLP_TOKEN_URL
GLP_BASE_URL=$GLP_BASE_URL

# PostgreSQL Settings
POSTGRES_USER=$POSTGRES_USER
POSTGRES_PASSWORD=$POSTGRES_PASSWORD
POSTGRES_DB=$POSTGRES_DB

# Scheduler Settings
SYNC_INTERVAL_MINUTES=$SYNC_INTERVAL_MINUTES
SYNC_DEVICES=$SYNC_DEVICES
SYNC_SUBSCRIPTIONS=$SYNC_SUBSCRIPTIONS
SYNC_ON_STARTUP=$SYNC_ON_STARTUP
SYNC_MAX_RETRIES=3
SYNC_RETRY_DELAY_MINUTES=5
HEALTH_CHECK_PORT=8080

# API Security Settings
# Development: DISABLE_AUTH=true bypasses authentication
# Production: Set DISABLE_AUTH=false and use API_KEY with X-API-Key header
DISABLE_AUTH=$DISABLE_AUTH
API_KEY=$API_KEY

# JWT Authentication (for Agent Chatbot API)
REQUIRE_AUTH=$REQUIRE_AUTH
JWT_SECRET=$JWT_SECRET
JWT_ALGORITHM=HS256
EOF

# Add LLM configuration if provider was selected
if [ -n "$LLM_PROVIDER" ]; then
    cat >> .env << EOF

# AI Chatbot Configuration
LLM_PROVIDER=$LLM_PROVIDER
LLM_MODEL=$LLM_MODEL
EOF

    if [ "$LLM_PROVIDER" = "anthropic" ]; then
        echo "ANTHROPIC_API_KEY=$LLM_API_KEY" >> .env
        if [ -n "$OPENAI_API_KEY" ]; then
            echo "OPENAI_API_KEY=$OPENAI_API_KEY" >> .env
            echo "EMBEDDING_MODEL=$EMBEDDING_MODEL" >> .env
        fi
    elif [ "$LLM_PROVIDER" = "openai" ]; then
        echo "OPENAI_API_KEY=$LLM_API_KEY" >> .env
        echo "EMBEDDING_MODEL=$EMBEDDING_MODEL" >> .env
    elif [ "$LLM_PROVIDER" = "ollama" ]; then
        echo "OLLAMA_BASE_URL=$OLLAMA_BASE_URL" >> .env
        echo "OLLAMA_MODEL=$LLM_MODEL" >> .env
    fi
fi

print_success ".env file created"

# Create frontend .env if in production mode (with API key)
if [ "$DISABLE_AUTH" = "false" ] && [ -n "$API_KEY" ]; then
    print_step "Creating frontend/.env with API key..."
    cat > frontend/.env << EOF
# Frontend Environment Variables
# Generated by setup.sh

# API Key for dashboard requests
VITE_API_KEY=$API_KEY
EOF
    print_success "frontend/.env created"
fi

# ============================================
# Build and Start
# ============================================
print_header "Step 8: Building & Starting Containers"

print_step "Building Docker images..."
docker compose build

echo ""
print_step "Starting containers..."
docker compose up -d

echo ""
print_success "Containers started!"

# ============================================
# Final Summary
# ============================================
print_header "Setup Complete! "

echo -e "${BOLD}Services Running:${NC}"
echo "  • PostgreSQL:   localhost:5432"
echo "  • Health Check: http://localhost:8080"
if [ -n "$LLM_PROVIDER" ]; then
    echo "  • AI Chatbot:   Configured with $LLM_PROVIDER"
fi
echo ""

echo -e "${BOLD}API Security:${NC}"
if [ "$DISABLE_AUTH" = "true" ]; then
    echo "  • Mode: Development (no authentication)"
else
    echo "  • Mode: Production"
    echo "  • API Key:    $API_KEY"
    echo "  • JWT Secret: $JWT_SECRET"
    echo ""
    echo -e "  ${YELLOW}IMPORTANT: Save these secrets!${NC}"
    echo -e "  ${CYAN}API Key: Use in X-API-Key header for dashboard/assignment APIs${NC}"
    echo -e "  ${CYAN}JWT Secret: Configured automatically for agent chatbot API${NC}"
fi
echo ""

echo -e "${BOLD}Useful Commands:${NC}"
echo "  View logs:              docker compose logs -f scheduler"
echo "  Check health:           curl http://localhost:8080/"
echo "  Stop services:          docker compose down"
echo "  Manual sync:            docker compose run --rm sync-once"
echo "  Check expiring subs:    docker compose run --rm check-expiring"
echo ""

echo -e "${BOLD}Next sync in:${NC} $SYNC_INTERVAL_MINUTES minutes"
echo ""

# Show initial logs
echo -e "${YELLOW}Showing scheduler logs (Ctrl+C to exit)...${NC}"
echo ""
sleep 2
docker compose logs -f scheduler