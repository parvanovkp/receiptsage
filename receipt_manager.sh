#!/bin/bash
# Receipt Manager Application
# A complete solution for managing and analyzing receipts

# Exit on any error
set -e

# Configuration
DB_PATH="receipts.db"
RECEIPTS_DIR="data/receipts"
ENV_FILE=".env"
PORT=8501  # Default Streamlit port

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Print colored message
print_msg() {
    color=$1
    msg=$2
    echo -e "${color}${msg}${NC}"
}

# Check for required environment file
check_env() {
    if [ ! -f "$ENV_FILE" ]; then
        print_msg $RED "Error: $ENV_FILE not found!"
        echo "Please create $ENV_FILE with the following content:"
        echo "OPENAI_API_KEY=your_api_key_here"
        exit 1
    fi
}

# Check for required Python packages
check_dependencies() {
    print_msg $BLUE "Checking dependencies..."
    python -c "import streamlit, openai, sqlalchemy, pandas" 2>/dev/null || {
        print_msg $RED "Error: Missing required Python packages"
        print_msg $YELLOW "Please ensure your conda environment has all required packages:"
        echo "streamlit, openai, sqlalchemy, pandas"
        exit 1
    }
}

# Create initial directory structure
setup_directories() {
    if [ ! -d "$RECEIPTS_DIR" ]; then
        print_msg $BLUE "Creating receipts directory..."
        mkdir -p "$RECEIPTS_DIR"
    fi
}

# Process new receipts
process_receipts() {
    print_msg $BLUE "Checking for new receipts..."
    if [ ! -d "$RECEIPTS_DIR" ]; then
        print_msg $RED "Error: Receipts directory not found!"
        print_msg $YELLOW "Run './receipt_manager.sh setup' first"
        exit 1
    fi
    python incremental_import.py "$RECEIPTS_DIR" --env "$ENV_FILE" --db "$DB_PATH"
}

# Launch dashboard
launch_dashboard() {
    print_msg $BLUE "Launching dashboard..."
    if [ ! -f "$DB_PATH" ]; then
        print_msg $YELLOW "Warning: Database not found. You may need to process receipts first."
    fi
    streamlit run dashboard.py --server.port "$PORT"
}

# Display help message
show_help() {
    echo "Receipt Manager - Usage:"
    echo "  ./receipt_manager.sh [command]"
    echo ""
    echo "Commands:"
    echo "  start       - Start the dashboard"
    echo "  process     - Process new receipts only"
    echo "  import      - Process and import new receipts"
    echo "  setup       - Set up the directory structure"
    echo "  help        - Show this help message"
    echo ""
    echo "Examples:"
    echo "  ./receipt_manager.sh start    # Start the dashboard"
    echo "  ./receipt_manager.sh process  # Process new receipts"
}

# Main execution
case "$1" in
    "start")
        check_env
        check_dependencies
        launch_dashboard
        ;;
    "process")
        check_env
        check_dependencies
        process_receipts
        ;;
    "import")
        check_env
        check_dependencies
        process_receipts
        ;;
    "setup")
        setup_directories
        check_env
        check_dependencies
        print_msg $GREEN "Setup complete!"
        ;;
    "help")
        show_help
        ;;
    *)
        show_help
        exit 1
        ;;
esac