import logging
import json
import traceback
from datetime import datetime
from django.conf import settings
from django.db import models
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey
from django.utils import timezone

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler('logs/app.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

class AuditLog(models.Model):
    ACTION_TYPES = (
        ('CREATE', 'Create'),
        ('UPDATE', 'Update'),
        ('DELETE', 'Delete'),
        ('LOGIN', 'Login'),
        ('LOGOUT', 'Logout'),
        ('VIEW', 'View'),
        ('ERROR', 'Error'),
        ('STATUS_CHANGE', 'Status Change'),
        ('APPOINTMENT_CREATE', 'Appointment Created'),
        ('APPOINTMENT_UPDATE', 'Appointment Updated'),
        ('APPOINTMENT_CANCEL', 'Appointment Cancelled'),
        ('APPOINTMENT_COMPLETE', 'Appointment Completed'),
        ('STAFF_SCHEDULE_UPDATE', 'Staff Schedule Updated'),
        ('SERVICE_UPDATE', 'Service Updated'),
    )

    user = models.ForeignKey('CustomUser', on_delete=models.SET_NULL, null=True)
    action = models.CharField(max_length=30, choices=ACTION_TYPES)
    timestamp = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField(null=True)
    user_agent = models.TextField(null=True)
    
    # For linking to any model
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, null=True)
    object_id = models.PositiveIntegerField(null=True)
    content_object = GenericForeignKey('content_type', 'object_id')
    
    # Additional details
    details = models.JSONField(null=True)
    endpoint = models.CharField(max_length=255, null=True)
    business = models.ForeignKey('Business', on_delete=models.SET_NULL, null=True)
    
    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['timestamp', 'action']),
            models.Index(fields=['user', 'action']),
            models.Index(fields=['content_type', 'object_id']),
            models.Index(fields=['business', 'action']),
        ]

    def __str__(self):
        return f"{self.action} by {self.user} at {self.timestamp}"

class ErrorLog(models.Model):
    SEVERITY_LEVELS = (
        ('CRITICAL', 'Critical'),
        ('ERROR', 'Error'),
        ('WARNING', 'Warning'),
        ('INFO', 'Info'),
        ('DEBUG', 'Debug'),
    )

    timestamp = models.DateTimeField(auto_now_add=True)
    severity = models.CharField(max_length=10, choices=SEVERITY_LEVELS)
    error_type = models.CharField(max_length=255)
    error_message = models.TextField()
    traceback = models.TextField()
    user = models.ForeignKey('CustomUser', on_delete=models.SET_NULL, null=True)
    endpoint = models.CharField(max_length=255, null=True)
    request_data = models.JSONField(null=True)
    business = models.ForeignKey('Business', on_delete=models.SET_NULL, null=True)
    handled = models.BooleanField(default=False)
    resolution_notes = models.TextField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(
        'CustomUser', 
        on_delete=models.SET_NULL, 
        null=True, 
        related_name='resolved_errors'
    )
    
    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['timestamp', 'severity']),
            models.Index(fields=['error_type']),
            models.Index(fields=['handled']),
            models.Index(fields=['business', 'severity']),
        ]

    def __str__(self):
        return f"{self.severity}: {self.error_type} at {self.timestamp}"

class LoggingService:
    @staticmethod
    def log_action(user, action, ip_address=None, user_agent=None, 
                  content_object=None, details=None, endpoint=None):
        """Log user actions"""
        try:
            business = None
            if hasattr(user, 'business'):
                business = user.business
            elif content_object and hasattr(content_object, 'business'):
                business = content_object.business

            AuditLog.objects.create(
                user=user,
                action=action,
                ip_address=ip_address,
                user_agent=user_agent,
                content_object=content_object,
                details=details,
                endpoint=endpoint,
                business=business
            )
            logger.info(f"Action logged: {action} by {user}")
        except Exception as e:
            logger.error(f"Failed to log action: {str(e)}")
            logger.error(traceback.format_exc())

    @staticmethod
    def log_error(error, severity, user=None, endpoint=None, request_data=None, business=None):
        """Log application errors"""
        try:
            error_type = type(error).__name__
            error_message = str(error)
            error_traceback = traceback.format_exc()

            # Create error log entry
            error_log = ErrorLog.objects.create(
                severity=severity,
                error_type=error_type,
                error_message=error_message,
                traceback=error_traceback,
                user=user,
                endpoint=endpoint,
                request_data=request_data,
                business=business
            )
            
            # Log to file system
            logger.error(f"{severity}: {error_type} - {error_message}\n{error_traceback}")

            # For critical errors, send notification
            if severity == 'CRITICAL':
                LoggingService.notify_admins_of_error(error_log)

        except Exception as e:
            logger.critical(f"Failed to log error: {str(e)}")
            logger.critical(traceback.format_exc())

    @staticmethod
    def notify_admins_of_error(error_log):
        """Notify administrators of critical errors"""
        try:
            from django.core.mail import send_mail
            from django.conf import settings

            subject = f"CRITICAL ERROR: {error_log.error_type}"
            message = f"""
            Business: {error_log.business.name if error_log.business else 'N/A'}
            Timestamp: {error_log.timestamp}
            Type: {error_log.error_type}
            Message: {error_log.error_message}
            Endpoint: {error_log.endpoint}
            User: {error_log.user.email if error_log.user else 'Anonymous'}
            
            Traceback:
            {error_log.traceback}
            """

            send_mail(
                subject,
                message,
                settings.DEFAULT_FROM_EMAIL,
                [admin[1] for admin in settings.ADMINS],
                fail_silently=True,
            )
        except Exception as e:
            logger.error(f"Failed to send admin notification: {str(e)}")

    @staticmethod
    def get_business_logs(business, start_date=None, end_date=None):
        """Get logs for a specific business"""
        if not start_date:
            start_date = timezone.now() - timezone.timedelta(days=30)
        if not end_date:
            end_date = timezone.now()

        return {
            'audit_logs': AuditLog.objects.filter(
                business=business,
                timestamp__range=[start_date, end_date]
            ),
            'error_logs': ErrorLog.objects.filter(
                business=business,
                timestamp__range=[start_date, end_date]
            )
        }

class LoggingMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Process request
        try:
            if hasattr(request, 'user') and request.user.is_authenticated:
                LoggingService.log_action(
                    user=request.user,
                    action='VIEW',
                    ip_address=request.META.get('REMOTE_ADDR'),
                    user_agent=request.META.get('HTTP_USER_AGENT'),
                    endpoint=request.path,
                    details={
                        'method': request.method,
                        'query_params': dict(request.GET),
                    }
                )
        except Exception as e:
            logger.error(f"Logging middleware request error: {str(e)}")

        response = self.get_response(request)

        # Process response
        if response.status_code >= 400:
            try:
                severity = 'ERROR' if response.status_code >= 500 else 'WARNING'
                business = getattr(request.user, 'business', None) if hasattr(request, 'user') else None
                
                LoggingService.log_error(
                    error=Exception(f"HTTP {response.status_code}"),
                    severity=severity,
                    user=request.user if hasattr(request, 'user') and request.user.is_authenticated else None,
                    endpoint=request.path,
                    request_data={
                        'method': request.method,
                        'path': request.path,
                        'query_params': dict(request.GET),
                    },
                    business=business
                )
            except Exception as e:
                logger.error(f"Logging middleware response error: {str(e)}")

        return response