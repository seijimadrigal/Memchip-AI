#!/bin/bash
set -euo pipefail

# MemChip Cloud — Deploy to VPS
VPS="root@76.13.23.55"
SSH="ssh -i ~/.ssh/hostinger_key -o StrictHostKeyChecking=no"
SCP="scp -i ~/.ssh/hostinger_key -o StrictHostKeyChecking=no"
REMOTE_DIR="/opt/memchip"

echo "🚀 Deploying MemChip Cloud to $VPS"

# 1. Create remote directory structure
echo "📁 Setting up remote directory..."
$SSH $VPS "mkdir -p $REMOTE_DIR/nginx/ssl"

# 2. Sync files to VPS
echo "📦 Syncing files..."
rsync -avz --delete \
    -e "ssh -i ~/.ssh/hostinger_key -o StrictHostKeyChecking=no" \
    --exclude '__pycache__' --exclude '*.pyc' --exclude '.git' --exclude '*.db' \
    "$(dirname "$(dirname "$0")")/" \
    $VPS:$REMOTE_DIR/

# 3. Create .env file on VPS
echo "🔐 Setting up environment..."
$SSH $VPS "cat > $REMOTE_DIR/cloud/.env << 'EOF'
OPENROUTER_API_KEY=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
LLM_MODEL=openai/gpt-4.1-mini
EMBEDDING_MODEL=all-MiniLM-L6-v2
EOF"

# 4. Build and start containers
echo "🐳 Building and starting containers..."
$SSH $VPS "cd $REMOTE_DIR/cloud && docker compose down 2>/dev/null || true"
$SSH $VPS "cd $REMOTE_DIR/cloud && docker compose build --no-cache api"
$SSH $VPS "cd $REMOTE_DIR/cloud && docker compose up -d"

# 5. Wait for services to be healthy
echo "⏳ Waiting for services..."
sleep 15

# 6. Seed the database (create default org + API key)
echo "🌱 Seeding database..."
$SSH $VPS "cd $REMOTE_DIR/cloud && docker compose exec -T api python -m app.seed"

# 7. Check health
echo "🏥 Health check..."
$SSH $VPS "curl -s http://localhost:8000/v1/health | python3 -m json.tool"

echo ""
echo "✅ MemChip Cloud deployed!"
echo "📍 API: http://76.13.23.55/v1/"
echo "📚 Docs: http://76.13.23.55/docs"
