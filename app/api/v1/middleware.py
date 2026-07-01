import uuid
import traceback
import json
import logging
from app.core.logging_config import request_id_var

logger = logging.getLogger("app.main")
error_file_logger = logging.getLogger("system_errors")

class ASGIRequestIDMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        # Extract X-Request-ID header if present
        request_id = None
        headers = scope.get("headers", [])
        for key, value in headers:
            if key == b"x-request-id":
                request_id = value.decode("utf-8", errors="ignore")
                break

        if not request_id:
            request_id = str(uuid.uuid4())

        # Bind request_id context variable for the duration of the ASGI request
        token = request_id_var.set(request_id)

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                resp_headers = list(message.get("headers", []))
                # Add X-Request-ID to response headers
                resp_headers.append((b"x-request-id", request_id.encode("utf-8")))
                message["headers"] = resp_headers
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception as exc:
            # Bulletproof exception handling at the ASGI level
            tb = traceback.format_exc()
            
            # Log to system_error.log
            try:
                error_file_logger.error(
                    f"Unhandled exception during {scope.get('method', 'GET')} {scope.get('path', '/')} [Request ID: {request_id}]: {str(exc)}\nTraceback:\n{tb}"
                )
            except Exception as e:
                logger.error(f"Failed to write to system_error.log: {str(e)}")
                
            # Log JSON format to console (stdout)
            logger.error(f"Unhandled exception at ASGI level: {str(exc)}", exc_info=exc)
            
            # Return HTTP 500 JSON response to ASGI client if connection is HTTP
            if scope["type"] == "http":
                try:
                    response_content = json.dumps({
                        "detail": "An internal server error occurred.",
                        "request_id": request_id
                    }).encode("utf-8")
                    
                    await send({
                        "type": "http.response.start",
                        "status": 500,
                        "headers": [
                            (b"content-type", b"application/json"),
                            (b"x-request-id", request_id.encode("utf-8"))
                        ]
                    })
                    await send({
                        "type": "http.response.body",
                        "body": response_content,
                        "more_body": False
                    })
                except Exception as send_err:
                    logger.error(f"Failed to send 500 error response to ASGI: {str(send_err)}")
            raise exc
        finally:
            request_id_var.reset(token)
