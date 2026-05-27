from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from scripts._common import load_dotenv


@dataclass(frozen=True)
class CloudConfig:
    aws_region: str
    s3_bucket: str
    database_url: str

    @classmethod
    def from_env(cls, dotenv_path: Path = Path(".env")) -> "CloudConfig":
        load_dotenv(dotenv_path)
        missing = [
            key
            for key in ("AWS_REGION", "S3_BUCKET", "DATABASE_URL")
            if not os.environ.get(key)
        ]
        if missing:
            raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")
        return cls(
            aws_region=os.environ["AWS_REGION"],
            s3_bucket=os.environ["S3_BUCKET"],
            database_url=os.environ["DATABASE_URL"],
        )
