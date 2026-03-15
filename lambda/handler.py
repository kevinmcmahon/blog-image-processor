import os
import urllib.parse
from io import BytesIO
from pathlib import PurePosixPath

import boto3
from PIL import Image

from aws_lambda_powertools import Logger, Metrics, Tracer
from aws_lambda_powertools.metrics import MetricUnit
from aws_lambda_powertools.utilities.data_classes import S3Event, event_source

logger = Logger(service="blog-image-processor")
tracer = Tracer(service="blog-image-processor")
metrics = Metrics(namespace="BlogImageProcessing", service="blog-image-processor")

s3_client = boto3.client("s3")

BASE_URL = os.environ.get("BASE_URL", "https://cache.kevfoo.com")

SKIP_EXTENSIONS = {".webp", ".html"}

EXTENSION_MIME_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
}


@logger.inject_lambda_context
@tracer.capture_lambda_handler
@metrics.log_metrics(capture_cold_start_metric=True)
@event_source(data_class=S3Event)
def lambda_handler(event: S3Event, context):
    for record in event.records:
        bucket = record.s3.bucket.name
        key = urllib.parse.unquote_plus(record.s3.get_object.key)

        path = PurePosixPath(key)
        ext = path.suffix.lower()

        if ext in SKIP_EXTENSIONS:
            logger.info("Skipping file to prevent loop", key=key, extension=ext)
            continue

        logger.info("Processing image", bucket=bucket, key=key)

        try:
            _process_image(bucket, key, path, ext)
            metrics.add_metric(name="ImagesProcessed", unit=MetricUnit.Count, value=1)
        except Exception:
            logger.exception("Failed to process image", key=key)
            metrics.add_metric(name="ProcessingErrors", unit=MetricUnit.Count, value=1)
            raise

    return {"statusCode": 200}


@tracer.capture_method
def _process_image(bucket: str, key: str, path: PurePosixPath, ext: str):
    # Download original from S3
    response = s3_client.get_object(Bucket=bucket, Key=key)
    image_bytes = response["Body"].read()

    # Convert to webp
    img = Image.open(BytesIO(image_bytes))
    webp_buffer = BytesIO()
    img.save(webp_buffer, format="WEBP", quality=85)

    # Upload webp
    webp_key = str(path.with_suffix(".webp"))
    s3_client.put_object(
        Bucket=bucket,
        Key=webp_key,
        Body=webp_buffer.getvalue(),
        ContentType="image/webp",
        ACL="public-read",
    )
    logger.info("Uploaded webp", key=webp_key)

    # Generate and upload HTML snippet
    name = path.stem
    src_type = EXTENSION_MIME_TYPES.get(ext, f"image/{ext.lstrip('.')}")
    original_url = f"{BASE_URL}/{key}"
    webp_url = f"{BASE_URL}/{webp_key}"

    html = (
        f'<p><picture>'
        f'<source type="image/webp" srcset="{webp_url}">'
        f'<source type="{src_type}" srcset="{original_url}">'
        f'<img src="{original_url}" title="{name}" alt="{name}" />'
        f'</picture></p>'
    )

    html_key = str(path.with_suffix(".html"))
    s3_client.put_object(
        Bucket=bucket,
        Key=html_key,
        Body=html.encode("utf-8"),
        ContentType="text/html",
        ACL="public-read",
    )
    logger.info("Uploaded HTML snippet", key=html_key)
