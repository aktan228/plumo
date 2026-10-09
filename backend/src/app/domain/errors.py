"""Application and domain errors.

API layer maps these to HTTP responses. Services raise them instead of
returning sentinel values.
"""


class AppError(Exception):
    """Base error with a stable machine code and an HTTP status."""

    code = "error"
    http_status = 400

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class CustomerNotFound(AppError):
    code = "customer_not_found"
    http_status = 404


class KnowledgeNotFound(AppError):
    code = "knowledge_not_found"
    http_status = 404


class ConversationNotFound(AppError):
    code = "conversation_not_found"
    http_status = 404


class HandoffNotFound(AppError):
    code = "handoff_not_found"
    http_status = 404


class MeetingNotFound(AppError):
    code = "meeting_not_found"
    http_status = 404


class BusinessNotFound(AppError):
    code = "business_not_found"
    http_status = 404


class InvalidMessage(AppError):
    code = "invalid_message"
    http_status = 422


class InvalidState(AppError):
    code = "invalid_state"
    http_status = 409


class CustomerConflict(InvalidState):
    """A concurrent request created the same customer first."""

    code = "customer_conflict"


class DuplicateMessage(InvalidState):
    """The same inbound message id arrived twice at once; the first copy wins."""

    code = "duplicate_message"


class ProviderUnavailable(AppError):
    code = "provider_unavailable"
    http_status = 503


class ProviderTransientError(ProviderUnavailable):
    """The model answered nothing usable this time: empty reply, 429, 5xx, timeout.

    The pipeline retries and degrades to a safe line. A wrong key or an empty
    balance stays ProviderUnavailable and fails loudly.
    """

    code = "provider_transient_error"


class UnsafeResponse(AppError):
    """Raised only by strict callers. The message pipeline converts this into a handoff."""

    code = "unsafe_response"
    http_status = 422


class HandoffRequired(AppError):
    """Signal that a human must take the dialog. The message API still returns 200."""

    code = "handoff_required"
    http_status = 409


class Unauthorized(AppError):
    """A webhook or provider callback failed authentication."""

    code = "unauthorized"
    http_status = 401
