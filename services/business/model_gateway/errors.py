class GatewayError(Exception):
    def __init__(self, code, message, status=502, *, diagnostic=None):
        self.code = code
        self.message = message
        self.status = status
        self.diagnostic = diagnostic or {}
        super().__init__(message)
