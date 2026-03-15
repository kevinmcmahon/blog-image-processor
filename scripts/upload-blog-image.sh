#!/usr/bin/env bash
set -euo pipefail

AWS_PROFILE="personal"
BUCKET="kevfoo-content"
BASE_URL="https://cache.kevfoo.com"

# Default to current year/month
YEAR=$(date +%Y)
MONTH=$(date +%m)

usage() {
    echo "Usage: $0 <file> [file2 ...] [-d YYYY/MM]"
    echo ""
    echo "Uploads images to s3://$BUCKET with Lambda-powered webp conversion."
    echo "Prints <picture> markdown for each image."
    echo ""
    echo "Options:"
    echo "  -d YYYY/MM   Override the date prefix (default: $YEAR/$MONTH)"
    echo ""
    echo "Examples:"
    echo "  $0 grandma-note.jpg grandma-recipe.jpg"
    echo "  $0 photo.jpg -d 2025/11"
    exit 1
}

if [[ $# -eq 0 ]]; then
    usage
fi

# Parse args
files=()
while [[ $# -gt 0 ]]; do
    case "$1" in
        -d)
            IFS='/' read -r YEAR MONTH <<< "$2"
            shift 2
            ;;
        -h|--help)
            usage
            ;;
        *)
            files+=("$1")
            shift
            ;;
    esac
done

if [[ ${#files[@]} -eq 0 ]]; then
    echo "Error: no files specified"
    usage
fi

for file in "${files[@]}"; do
    if [[ ! -f "$file" ]]; then
        echo "Error: $file not found"
        exit 1
    fi

    filename=$(basename "$file")
    name="${filename%.*}"
    ext="${filename##*.}"
    ext_lower=$(echo "$ext" | tr '[:upper:]' '[:lower:]')
    s3_path="s3://$BUCKET/$YEAR/$MONTH/$filename"
    url="$BASE_URL/$YEAR/$MONTH/$filename"

    # Upload original
    echo "Uploading $filename -> $s3_path"
    AWS_PROFILE="$AWS_PROFILE" aws s3 cp "$file" "$s3_path" --acl public-read

    # Wait for Lambda to generate the HTML snippet
    snippet_key="$YEAR/$MONTH/$name.html"
    snippet_s3="s3://$BUCKET/$snippet_key"
    echo "Waiting for Lambda to process..."
    for i in {1..5}; do
        sleep 3
        if AWS_PROFILE="$AWS_PROFILE" aws s3 ls "$snippet_s3" &>/dev/null; then
            snippet=$(AWS_PROFILE="$AWS_PROFILE" aws s3 cp "$snippet_s3" -)
            echo ""
            echo "Markdown:"
            echo "$snippet"
            echo "$snippet" | pbcopy
            echo "(copied to clipboard)"
            break
        fi
        if [[ $i -eq 5 ]]; then
            # Fallback: generate snippet locally if Lambda hasn't run yet
            echo "Lambda hasn't processed yet. Generating snippet locally..."
            webp_url="$BASE_URL/$YEAR/$MONTH/$name.webp"
            case "$ext_lower" in
                jpg|jpeg) src_type="image/jpeg" ;;
                png)      src_type="image/png" ;;
                gif)      src_type="image/gif" ;;
                *)        src_type="image/$ext_lower" ;;
            esac
            snippet="<p><picture><source type=\"image/webp\" srcset=\"$webp_url\"><source type=\"$src_type\" srcset=\"$url\"><img src=\"$url\" title=\"$name\" alt=\"$name\" /></picture></p>"
            echo ""
            echo "Markdown:"
            echo "$snippet"
            echo "$snippet" | pbcopy
            echo "(copied to clipboard)"
        fi
    done

    echo ""
done
