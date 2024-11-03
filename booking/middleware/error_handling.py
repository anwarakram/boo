import traceback
from django.http import JsonResponse
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework.exceptions import ValidationError as DRFValidationError
from ..exceptions import BookingBaseException
from ..logging_system import LoggingService

class ErrorHandlingMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        try:
            response = self.get_response(request)
            return response
        except Exception as e:
            return self.handle_error(request, e)

    def handle_error(self, request, exc):
        """
        Handles different types of exceptions and returns appropriate responses
        """
        if isinstance(exc, BookingBaseException):
            error_data = {
                'error': exc.default_code,
                'message': str(exc.detail),
                'status': exc.status_code
            }
            status_code = exc.status_code
        
        elif isinstance(exc, (DjangoValidationError, DRFValidationError)):
            error_data = {
                'error': 'validation_error',
                'message': str(exc),
                'status': 400
            }
            status_code = 400
            
        else:
            # Handle unexpected errors
            status_code = 500
            error_data = {
                'error': 'internal_server_error',
                'message': 'An unexpected error occurred.',
                'status': status_code
            }
            if settings.DEBUG:
                error_data['debug'] = {
                    'exception': str(exc),
                    'traceback': traceback.format_exc()
                }

        # Log the error
        severity = 'ERROR' if status_code >= 500 else 'WARNING'
        LoggingService.log_error(
            error=exc,
            severity=severity,
            user=request.user if hasattr(request, 'user') else None,
            endpoint=request.path,
            request_data={
                'method': request.method,
                'path': request.path,
                'query_params': dict(request.GET),
                'body': request.POST or None,
            }
        )

        return JsonResponse(error_data, status=status_code)