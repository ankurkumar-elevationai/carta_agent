class SessionExpiredError(Exception):
    """Raised when the Carta session is invalid or redirected to the login domain."""
    pass

class InvalidRouteError(Exception):
    """Raised when navigation lands on an invalid route or 404 page."""
    pass

class PersonaMismatchError(Exception):
    """Raised when the loaded persona does not match the expected capabilities."""
    pass
