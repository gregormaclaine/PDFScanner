import time
import uuid
import logging
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from pythonjsonlogger import jsonlogger
from fastapi import Request

# 1. SETUP STRUCTURED LOGGING (No sensitive content)
logger = logging.getLogger("secure_api")
logger.setLevel(logging.INFO)
logHandler = logging.StreamHandler()
formatter = jsonlogger.JsonFormatter('%(timestamp)s %(levelname)s %(message)s %(request_id)s %(method)s %(path)s %(status_code)s %(processing_time)s')
logHandler.setFormatter(formatter)
logger.addHandler(logHandler)

class SecurityAuditMiddleware(BaseHTTPMiddleware):
    """
    Production-grade security middleware:
    - Structured logging (no sensitive content)
    - Security headers (nosniff, HSTS, frame-options)
    - Request ID tracking
    - Global error shielding
    """
    async def dispatch(self, request: Request, call_next):
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        start_time = time.time()
        
        try:
            response = await call_next(request)
            process_time = time.time() - start_time
            
            # 2. ADD SECURITY HEADERS
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["X-Frame-Options"] = "DENY"
            response.headers["Strict-Transport-Security"] = "max-age=31536000 ; includeSubDomains"
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; "
                "script-src 'self' 'unsafe-inline' cdn.jsdelivr.net; "
                "style-src 'self' 'unsafe-inline' cdn.jsdelivr.net; "
                "img-src 'self' data: fastly.jsdelivr.net; "
                "frame-ancestors 'none'; "
                "object-src 'none'"
            )
            response.headers["X-Request-ID"] = request_id
            
            # 3. STRUCTURED LOGGING (Sanitized)
            logger.info("request_completed", extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "processing_time": f"{process_time:.4f}s",
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            })
            
            return response
            
        except Exception as e:
            # 4. GLOBAL ERROR SHIELDING (Production-safe)
            # Logs exception TYPE only — never logs document content
            logger.error("internal_error", extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "error": "Internal processing failure",
                "error_type": type(e).__name__,  # e.g. "ValueError", "TimeoutError" — safe to log
                "error_detail": str(e)[:200],    # First 200 chars only for diagnosis
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            })
            
            return JSONResponse(
                status_code=500,
                content={
                    "detail": "An unexpected internal processing failure occurred. Support tracking ID: " + request_id
                }
            )
