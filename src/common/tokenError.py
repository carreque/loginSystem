class TokenError(Exception):
    """Raised when a token fails verification (signature/exp/aud/iss/use)."""
