#!/bin/bash

echo "Starting environment setup..."

# Extract directory name and create volume name
working_directory="$PWD"
current_dir_name=$(basename "$PWD")
db_volume="${current_dir_name}_pgvolume"
db_prune=true
fetch_main=false
cleanse_all=false

# Function to display help message
show_help() {
    echo "Usage: $0 [options]"
    echo ""
    echo "This script sets up your Django project environment using Docker Compose."
    echo "It performs the following actions:"
    echo "  - Stops and removes existing containers and volumes."
    echo "  - Cleans and initializes the project."
    echo "  - Builds the project and installs pre-commit hooks."
    echo "  - Starts Docker containers in the background."
    echo "  - Applies database migrations and creates a superuser."
    echo "  - Generates sample data and indexes Elasticsearch."
    echo "  - Stops the containers and opens the project in your code editor."
    echo ""
    echo "Options:"
    echo "  -h, --help   Show this help message and exit."
    echo "  -m, --main   Fetch the latest changes from origin/main and reset local files."
    echo "  -d, --dir    Specify the working directory (default: current directory)."
    echo "  -n, --no-db  Skip database purge and setup (useful for frontend-only projects)."
    echo "  -c, --cleansing-fire  Remove all Docker containers, images, and volumes."
}

# Function to display a simple progress indicator (no spinner this time)
show_progress() {
    echo -n "$1  " # Print the message without newline
    dots="....."
    for ((i=0; i<${#dots}; i++)); do
        echo -n "${dots:$i:1}"
        sleep 0.5  # Adjust sleep duration as needed
    done
}

# Function to check if a command was successful and handle errors
run_command() {
    message="$1"
    shift  # Remove the message from the argument list
    
    show_progress "$message" # Show simple progress indicator
    
    if ! "$@"; then
        echo -e "\r\033[K\e[31mError: $message failed.\e[0m"
        exit 1
    fi
    
    echo -e "\r\033[K\e[32mSuccess!\e[0m"
}


# --- Main Script ---

# Handle command-line arguments (check for -h or --help)
while [[ $# -gt 0 ]]; do
    case "$1" in
        -h|--help)
            show_help
            exit 0
        ;;
        -m|--main)
            fetch_main=true
        ;;
        -d|--dir)
            if [[ -d "$2" ]]; then
                working_directory="$2"
                shift
            else
                echo "Error: Directory '$2' not found."
                exit 1
            fi
        ;;
        -n|--no-db)
            db_prune=false
        ;;
        -c|--cleansing-fire)
            cleanse_all=true
        ;;
        *)
            echo "Unknown option: $1"
            show_help
            exit 1
        ;;
    esac
    shift
done

echo "Going to working directory..."
cd "$working_directory" || exit 1

# Fetch and reset if --main flag is present
if $fetch_main; then
    run_command "Fetching latest from origin/main..." git fetch origin main
    run_command "Resetting local files to match origin/main..." git reset --hard origin/main
fi

run_command "Stopping existing containers..." docker compose down  # Remove the spinner from here

if $cleanse_all; then
    run_command "Removing all containers..." docker rm -f $(docker ps -aq)
    run_command "Removing all images..." docker rmi -f $(docker images -aq)
    run_command "Removing all volumes..." docker volume prune -f
fi

if $db_prune; then
    if docker volume inspect "$db_volume" &> /dev/null; then
        run_command "Removing volume: $db_volume" docker volume rm "$db_volume"
    fi
fi

run_command "Cleaning project files..." make clean
run_command "Initializing project..." make init
run_command "Building project..." make build
run_command "Installing pre-commit hooks..." pre-commit install
run_command "Starting Docker containers..." docker compose up -d
run_command "Applying database migrations..." docker compose exec web ./manage.py makemigrations
run_command "Migrating database..." docker compose exec web ./manage.py migrate
run_command "Creating superuser..." docker compose exec web ./manage.py createsuperuser --noinput --username kitsune --email kitsune@mozilla.com
run_command "Generating sample data..." docker compose exec web ./manage.py generatedata

#run_command "Initializing Elasticsearch..." docker compose exec web ./manage.py es_init
#run_command "Reindexing Elasticsearch..." docker compose exec web ./manage.py es_reindex

docker compose down  # Remove the spinner from here
echo "Opening project in code editor..."
code .
echo "Setup complete!"
