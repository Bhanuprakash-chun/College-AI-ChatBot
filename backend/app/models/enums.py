"""Shared enumerations used across models and schemas."""

from enum import Enum


class UserRole(str, Enum):
    """Role names. New roles (e.g. FACULTY) can be added without schema churn."""

    STUDENT = "student"
    ADMIN = "admin"


class DocumentStatus(str, Enum):
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class DocumentType(str, Enum):
    POLICY = "policy"
    CIRCULAR = "circular"
    SYLLABUS = "syllabus"
    HANDBOOK = "handbook"
    NOTICE = "notice"
    REPORT = "report"
    OTHER = "other"


class FeedbackRating(str, Enum):
    UP = "up"
    DOWN = "down"


class MessageRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
