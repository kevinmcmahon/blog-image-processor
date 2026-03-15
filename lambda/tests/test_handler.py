from io import BytesIO

import boto3
import pytest
from moto import mock_aws
from PIL import Image

BUCKET = "test-bucket"


class FakeLambdaContext:
    function_name = "blog-image-processor"
    memory_limit_in_mb = 512
    invoked_function_arn = "arn:aws:lambda:us-east-1:123456789012:function:blog-image-processor"
    aws_request_id = "fake-request-id"


def make_s3_event(bucket, key):
    return {
        "Records": [
            {
                "eventSource": "aws:s3",
                "eventName": "ObjectCreated:Put",
                "s3": {
                    "bucket": {"name": bucket},
                    "object": {"key": key, "size": 1024},
                },
            }
        ]
    }


def create_test_image(fmt="JPEG", color="red"):
    """Create a small test image and return its bytes."""
    img = Image.new("RGB", (100, 100), color)
    buf = BytesIO()
    img.save(buf, format=fmt)
    buf.seek(0)
    return buf.getvalue()


@pytest.fixture
def s3(monkeypatch):
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_SECURITY_TOKEN", "testing")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "testing")
    monkeypatch.setenv("POWERTOOLS_TRACE_DISABLED", "1")
    monkeypatch.setenv("POWERTOOLS_METRICS_NAMESPACE", "test")

    with mock_aws():
        client = boto3.client("s3", region_name="us-east-1")
        client.create_bucket(Bucket=BUCKET)
        yield client


def _invoke_handler(event):
    """Import and call the handler, avoiding module-level tracer issues."""
    from handler import lambda_handler

    return lambda_handler(event, FakeLambdaContext())


class TestWebpConversion:
    def test_jpg_produces_webp(self, s3):
        key = "2026/03/photo.jpg"
        s3.put_object(Bucket=BUCKET, Key=key, Body=create_test_image("JPEG"))

        _invoke_handler(make_s3_event(BUCKET, key))

        webp_obj = s3.get_object(Bucket=BUCKET, Key="2026/03/photo.webp")
        webp_bytes = webp_obj["Body"].read()
        img = Image.open(BytesIO(webp_bytes))
        assert img.format == "WEBP"

    def test_png_produces_webp(self, s3):
        key = "2026/03/screenshot.png"
        s3.put_object(Bucket=BUCKET, Key=key, Body=create_test_image("PNG"))

        _invoke_handler(make_s3_event(BUCKET, key))

        webp_obj = s3.get_object(Bucket=BUCKET, Key="2026/03/screenshot.webp")
        webp_bytes = webp_obj["Body"].read()
        img = Image.open(BytesIO(webp_bytes))
        assert img.format == "WEBP"


class TestLoopPrevention:
    def test_webp_file_is_skipped(self, s3):
        key = "2026/03/photo.webp"
        s3.put_object(Bucket=BUCKET, Key=key, Body=b"fake webp data")

        _invoke_handler(make_s3_event(BUCKET, key))

        # No additional files should be created
        objects = s3.list_objects_v2(Bucket=BUCKET)
        keys = [o["Key"] for o in objects.get("Contents", [])]
        assert keys == ["2026/03/photo.webp"]

    def test_html_file_is_skipped(self, s3):
        key = "2026/03/photo.html"
        s3.put_object(Bucket=BUCKET, Key=key, Body=b"<p>snippet</p>")

        _invoke_handler(make_s3_event(BUCKET, key))

        objects = s3.list_objects_v2(Bucket=BUCKET)
        keys = [o["Key"] for o in objects.get("Contents", [])]
        assert keys == ["2026/03/photo.html"]


class TestHtmlSnippet:
    def test_html_snippet_content(self, s3, monkeypatch):
        monkeypatch.setenv("BASE_URL", "https://cache.kevfoo.com")
        # Re-import to pick up env change
        import handler
        handler.BASE_URL = "https://cache.kevfoo.com"

        key = "2026/03/grandma-note.jpg"
        s3.put_object(Bucket=BUCKET, Key=key, Body=create_test_image("JPEG"))

        _invoke_handler(make_s3_event(BUCKET, key))

        html_obj = s3.get_object(Bucket=BUCKET, Key="2026/03/grandma-note.html")
        html = html_obj["Body"].read().decode("utf-8")

        expected = (
            '<p><picture>'
            '<source type="image/webp" srcset="https://cache.kevfoo.com/2026/03/grandma-note.webp">'
            '<source type="image/jpeg" srcset="https://cache.kevfoo.com/2026/03/grandma-note.jpg">'
            '<img src="https://cache.kevfoo.com/2026/03/grandma-note.jpg" title="grandma-note" alt="grandma-note" />'
            '</picture></p>'
        )
        assert html == expected

    def test_png_mime_type_in_snippet(self, s3):
        import handler
        handler.BASE_URL = "https://cache.kevfoo.com"

        key = "2026/03/diagram.png"
        s3.put_object(Bucket=BUCKET, Key=key, Body=create_test_image("PNG"))

        _invoke_handler(make_s3_event(BUCKET, key))

        html_obj = s3.get_object(Bucket=BUCKET, Key="2026/03/diagram.html")
        html = html_obj["Body"].read().decode("utf-8")

        assert 'type="image/png"' in html
        assert 'type="image/webp"' in html


class TestErrorHandling:
    def test_conversion_failure_raises(self, s3):
        key = "2026/03/corrupt.jpg"
        s3.put_object(Bucket=BUCKET, Key=key, Body=b"not a real image")

        with pytest.raises(Exception):
            _invoke_handler(make_s3_event(BUCKET, key))
