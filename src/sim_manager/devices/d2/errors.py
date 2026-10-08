"""Closed, privacy-safe errors shared by D2 infrastructure and services."""


class D2SessionError(Exception):
    message = "Router request failed."

    def __init__(self, *_ignored: object) -> None:
        # Never echo a lower-level exception, password, response, or token.
        super().__init__(self.message)


class D2AuthenticationRejected(D2SessionError):
    message = "Router sign-in was rejected."


class D2MalformedAuthentication(D2SessionError, ValueError):
    message = "Router sign-in returned an invalid response."


class D2MissingSessionToken(D2MalformedAuthentication):
    message = "Router sign-in returned no valid session."


class D2AuthenticationRequired(D2SessionError, PermissionError):
    message = "Router authentication required."


class D2Timeout(D2SessionError, TimeoutError):
    message = "Router request timed out."


class D2Unreachable(D2SessionError, ConnectionError):
    message = "Router unreachable."


class D2ConnectionError(D2SessionError, ConnectionError):
    message = "Router TLS or connection problem."


class D2Cancelled(D2SessionError):
    message = "Router request cancelled."


class D2MalformedResponse(D2SessionError, ValueError):
    message = "Router returned an invalid response."


class D2ResponseTooLarge(D2MalformedResponse):
    message = "Router response exceeded its limit."
