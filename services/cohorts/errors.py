class Rejected(Exception):
    """A domain failure that maps to a client-facing HTTP status."""

    def __init__(self, status, message):
        super().__init__(message)
        self.status = status
