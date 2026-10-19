from __future__ import annotations


class DomainError(Exception):
    """Base error carrying an HTTP-safe message."""


class NotFoundError(DomainError):
    pass


class ConflictError(DomainError):
    pass


class ValidationError(DomainError):
    pass


class ForbiddenError(DomainError):
    pass
