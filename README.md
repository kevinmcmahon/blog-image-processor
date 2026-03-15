# blog-image-processor

Lambda that automatically converts blog images to `.webp` and generates `<picture>` HTML snippets when images are uploaded to S3.

## How it works

1. Upload a `.jpg`, `.jpeg`, or `.png` to your S3 bucket under `YYYY/MM/`
2. S3 triggers the Lambda via bucket notification
3. Lambda downloads the image, converts to webp (Pillow, quality=85), and uploads:
   - `YYYY/MM/filename.webp` — the converted image
   - `YYYY/MM/filename.html` — a `<picture>` snippet ready to paste into a blog post

The HTML snippet looks like:

```html
<p><picture>
  <source type="image/webp" srcset="https://cache.kevfoo.com/2026/03/photo.webp">
  <source type="image/jpeg" srcset="https://cache.kevfoo.com/2026/03/photo.jpg">
  <img src="https://cache.kevfoo.com/2026/03/photo.jpg" title="photo" alt="photo" />
</picture></p>
```

## Upload script

A companion CLI script handles the full workflow:

```bash
# Upload one or more images (uses current YYYY/MM by default)
upload-blog-image.sh photo.jpg diagram.png

# Override the date prefix
upload-blog-image.sh photo.jpg -d 2025/11
```

The script uploads the original with `public-read` ACL, waits for the Lambda to generate the HTML snippet, fetches it, prints it, and copies it to the clipboard.

## Project structure

```
lambda/
  handler.py           # Lambda function (convert + snippet in one)
  requirements.txt     # Pillow, aws-lambda-powertools
  tests/
    test_handler.py    # pytest + moto tests
terraform/
  providers.tf         # AWS provider config
  variables.tf         # Configurable bucket, URL, memory, timeout
  lambda.tf            # Lambda, IAM role, S3 notification, CloudWatch logs
  outputs.tf           # Function ARN, name, log group
  terraform.tfvars     # bucket and domain config
```

## Infrastructure

Deployed via Terraform. Resources:

- **Lambda**: `blog-image-processor` (Python 3.12, arm64, 512MB, 60s timeout, X-Ray tracing)
- **IAM role**: S3 read/write/ACL on the configured bucket, CloudWatch Logs, X-Ray, CloudWatch metrics
- **S3 notification**: triggers on `ObjectCreated:Put` for `.jpg`, `.jpeg`, `.png` suffixes
- **CloudWatch log group**: 14-day retention

The S3 bucket and CloudFront distribution are managed separately and not included in this Terraform.

## Deploy

### Prerequisites

- AWS CLI configured
- Terraform 1.0+
- uv (for installing Lambda dependencies)

### Build and deploy

```bash
cd lambda

# Install dependencies for Lambda (arm64 Linux)
uv pip install \
  --python-platform manylinux_2_28_aarch64 \
  --python-version 3.12 \
  --target package \
  -r requirements.txt

# Remove packages already in Lambda runtime
rm -rf package/{botocore,urllib3,jmespath,python_dateutil*,dateutil,six*}

# Copy handler and create zip
cp handler.py package/
cd package && zip -r9 ../package.zip . -x '__pycache__/*' '*.pyc' '*.dist-info/*'
cd ../..

# Deploy
cd terraform
terraform init
terraform plan
terraform apply
```

### Update Lambda code only

After changing `handler.py`:

```bash
cd lambda
cp handler.py package/
rm package.zip
cd package && zip -r9 ../package.zip . -x '__pycache__/*' '*.pyc' '*.dist-info/*'
cd ../../terraform
terraform apply
```

## Run tests

```bash
cd lambda
uv run pytest tests/ -v
```

