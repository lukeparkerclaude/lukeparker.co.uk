#!/bin/bash
# Convenience script to run the Luke Parker content pipeline
# Usage: ./run.sh [options]

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Get script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}Error: Python 3 is not installed${NC}"
    exit 1
fi

# Check if API key is set
if [ -z "$ANTHROPIC_API_KEY" ]; then
    if [ -f ".env" ]; then
        echo -e "${YELLOW}Loading API key from .env file...${NC}"
        set -a
        source .env
        set +a
    else
        echo -e "${RED}Error: ANTHROPIC_API_KEY environment variable not set${NC}"
        echo -e "${YELLOW}Please set it with: export ANTHROPIC_API_KEY='sk-ant-...'${NC}"
        echo -e "${YELLOW}Or create .env file with: cp .env.example .env${NC}"
        exit 1
    fi
fi

# Check if dependencies are installed
if ! python3 -c "import feedparser" 2>/dev/null; then
    echo -e "${YELLOW}Installing dependencies...${NC}"
    pip install -q -r requirements.txt
fi

# Parse command line arguments
DRY_RUN=""
LIMIT=""
VERBOSE=""
HELP=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --dry-run)
            DRY_RUN="--dry-run"
            shift
            ;;
        --limit)
            LIMIT="--limit $2"
            shift 2
            ;;
        --force-refresh)
            FORCE="--force-refresh"
            shift
            ;;
        --verbose|-v)
            VERBOSE="--verbose"
            shift
            ;;
        --test-feeds)
            python3 scripts/test_feeds.py "$2"
            exit 0
            ;;
        --help|-h)
            HELP=true
            shift
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            HELP=true
            break
            ;;
    esac
done

if [ "$HELP" = true ]; then
    echo "Luke Parker Content Pipeline Runner"
    echo ""
    echo "Usage: ./run.sh [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --dry-run          Preview changes without publishing"
    echo "  --limit N          Process maximum N articles"
    echo "  --force-refresh    Ignore deduplication"
    echo "  --verbose, -v      Enable debug logging"
    echo "  --test-feeds [FEED] Test RSS feeds"
    echo "  --help, -h         Show this help message"
    echo ""
    echo "Examples:"
    echo "  ./run.sh                              # Normal run"
    echo "  ./run.sh --dry-run --limit 5          # Preview 5 articles"
    echo "  ./run.sh --verbose                    # Debug mode"
    echo "  ./run.sh --test-feeds 'BBC News'      # Test specific feed"
    echo ""
    exit 0
fi

# Display run info
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Luke Parker Content Pipeline${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

if [ -n "$DRY_RUN" ]; then
    echo -e "${YELLOW}Mode: DRY RUN (no files will be published)${NC}"
fi

if [ -n "$LIMIT" ]; then
    echo "Limit: $LIMIT"
fi

if [ -n "$VERBOSE" ]; then
    echo "Logging: Verbose"
fi

echo ""

# Run the pipeline
python3 scripts/content_pipeline.py $DRY_RUN $LIMIT $FORCE $VERBOSE

exit_code=$?

echo ""
if [ $exit_code -eq 0 ]; then
    echo -e "${GREEN}Pipeline completed successfully${NC}"
else
    echo -e "${RED}Pipeline failed with exit code $exit_code${NC}"
fi

exit $exit_code
