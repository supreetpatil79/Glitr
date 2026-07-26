"""
models.py — SQLAlchemy ORM definition for the `jobs` table.
"""
import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, Text, func
import uuid as _uuid_module
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from db import Base


class JobStatus(str, enum.Enum):
    pending = "pending"
    processing = "processing"
    completed = "completed"
    failed = "failed"


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=_uuid_module.uuid4,
    )
    product_name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    reference_image_url = mapped_column(Text, nullable=True)
    generated_prompt = mapped_column(Text, nullable=True)
    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus, name="jobstatus"),
        nullable=False,
        default=JobStatus.pending,
        server_default=JobStatus.pending.value,
    )
    result_image_url = mapped_column(Text, nullable=True)
    error_message = mapped_column(Text, nullable=True)
    created_at = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "product_name": self.product_name,
            "description": self.description,
            "reference_image_url": self.reference_image_url,
            "generated_prompt": self.generated_prompt,
            "status": self.status.value if self.status else None,
            "result_image_url": self.result_image_url,
            "error_message": self.error_message,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
