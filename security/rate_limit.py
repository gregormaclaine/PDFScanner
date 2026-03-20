from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from fastapi import FastAPI, Response, Request

# Rate Limiter setup - 10 per minute default for security
limiter = Limiter(key_func=get_remote_address, default_limits=["10 per minute"])

def setup_rate_limiting(app: FastAPI):
    """Integrates slowapi rate limiting into the FastAPI application."""
    app.state.limiter = limiter
    # Provide custom handler to ensure internal server details aren't leaked
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
