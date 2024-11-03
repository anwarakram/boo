from datetime import datetime, timedelta
from django.db import models
from django.utils import timezone
from django.db.models import Avg, Count, F, Sum, ExpressionWrapper, fields
from .logging_system import LoggingService
from .models import (
    AppointmentService, Appointment, Schedule,
    Business, CustomUser, Service
)

class SystemMetrics(models.Model):
    timestamp = models.DateTimeField(auto_now_add=True)
    endpoint = models.CharField(max_length=255)
    response_time = models.FloatField()  # in seconds
    status_code = models.IntegerField()
    memory_usage = models.FloatField()  # in MB
    cpu_usage = models.FloatField()  # percentage
    database_queries = models.IntegerField()
    cache_hits = models.IntegerField()
    cache_misses = models.IntegerField()

    class Meta:
        indexes = [
            models.Index(fields=['timestamp', 'endpoint']),
        ]

class StaffActivityMetrics(models.Model):
    staff = models.ForeignKey('CustomUser', on_delete=models.CASCADE)
    session_start = models.DateTimeField()
    session_end = models.DateTimeField(null=True)
    appointments_created = models.IntegerField(default=0)
    appointments_completed = models.IntegerField(default=0)
    appointments_cancelled = models.IntegerField(default=0)
    total_revenue = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    browser_info = models.JSONField()
    device_info = models.JSONField()

class PerformanceMetrics(models.Model):
    timestamp = models.DateTimeField(auto_now_add=True)
    business = models.ForeignKey('Business', on_delete=models.CASCADE)
    total_appointments = models.IntegerField(default=0)
    completed_appointments = models.IntegerField(default=0)
    cancelled_appointments = models.IntegerField(default=0)
    total_revenue = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    avg_appointment_duration = models.DurationField(null=True)
    busiest_hour = models.IntegerField(null=True)
    staff_count = models.IntegerField(default=0)
    service_count = models.IntegerField(default=0)

class MonitoringService:
    @staticmethod
    def track_staff_session(staff, session_data):
        """Track staff session activity"""
        return StaffActivityMetrics.objects.create(
            staff=staff,
            session_start=timezone.now(),
            browser_info=session_data.get('browser_info', {}),
            device_info=session_data.get('device_info', {})
        )

    @staticmethod
    def update_staff_metrics(staff_metric, action_type):
        """Update ongoing staff metrics"""
        if action_type == 'CREATE_APPOINTMENT':
            staff_metric.appointments_created += 1
        elif action_type == 'COMPLETE_APPOINTMENT':
            staff_metric.appointments_completed += 1
        elif action_type == 'CANCEL_APPOINTMENT':
            staff_metric.appointments_cancelled += 1
        
        staff_metric.save()

    @staticmethod
    def end_staff_session(staff_metric):
        """End staff session tracking"""
        staff_metric.session_end = timezone.now()
        staff_metric.save()

    @staticmethod
    def track_system_metrics(request, response, start_time):
        """Track system performance metrics"""
        end_time = timezone.now()
        response_time = (end_time - start_time).total_seconds()

        SystemMetrics.objects.create(
            endpoint=request.path,
            response_time=response_time,
            status_code=response.status_code,
            memory_usage=get_memory_usage(),
            cpu_usage=get_cpu_usage(),
            database_queries=get_query_count(),
            cache_hits=get_cache_hits(),
            cache_misses=get_cache_misses()
        )

    @staticmethod
    def generate_business_report(business, start_date=None, end_date=None):
        """Generate comprehensive business performance report"""
        if not start_date:
            start_date = timezone.now() - timedelta(days=30)
        if not end_date:
            end_date = timezone.now()

        return {
            'appointments': analyze_appointments(business, start_date, end_date),
            'staff': analyze_staff_performance(business, start_date, end_date),
            'services': analyze_services(business, start_date, end_date),
            'revenue': analyze_revenue(business, start_date, end_date)
        }

    @staticmethod
    def generate_staff_report(staff, start_date=None, end_date=None):
        """Generate individual staff performance report"""
        if not start_date:
            start_date = timezone.now() - timedelta(days=30)
        if not end_date:
            end_date = timezone.now()

        services = AppointmentService.objects.filter(
            staff=staff,
            start_time__range=[start_date, end_date]
        )

        return {
            'total_appointments': services.count(),
            'completed_appointments': services.filter(
                appointment__status='COMPLETED'
            ).count(),
            'cancelled_appointments': services.filter(
                appointment__status='CANCELLED'
            ).count(),
            'total_revenue': services.aggregate(
                total=Sum('price')
            )['total'] or 0,
            'average_daily_appointments': services.count() / max(
                (end_date - start_date).days, 1
            ),
            'service_breakdown': analyze_staff_services(services),
            'hourly_performance': analyze_staff_hours(services),
        }

def analyze_appointments(business, start_date, end_date):
    """Analyze appointment patterns"""
    appointments = Appointment.objects.filter(
        business=business,
        created_at__range=[start_date, end_date]
    )

    return {
        'total': appointments.count(),
        'completed': appointments.filter(status='COMPLETED').count(),
        'cancelled': appointments.filter(status='CANCELLED').count(),
        'by_day': appointments.annotate(
            day=models.functions.Extract('created_at', 'day')
        ).values('day').annotate(count=Count('id')),
        'by_hour': appointments.annotate(
            hour=models.functions.Extract('created_at', 'hour')
        ).values('hour').annotate(count=Count('id')),
    }

def analyze_staff_performance(business, start_date, end_date):
    """Analyze staff performance metrics"""
    services = AppointmentService.objects.filter(
        appointment__business=business,
        start_time__range=[start_date, end_date]
    )

    return services.values(
        'staff__id',
        'staff__email',
        'staff__first_name',
        'staff__last_name'
    ).annotate(
        total_appointments=Count('id'),
        completed_appointments=Count(
            'id',
            filter=models.Q(appointment__status='COMPLETED')
        ),
        cancelled_appointments=Count(
            'id',
            filter=models.Q(appointment__status='CANCELLED')
        ),
        total_revenue=Sum('price'),
        avg_daily_appointments=Count('id') / models.F('total_days')
    ).annotate(
        total_days=models.Value(
            (end_date - start_date).days,
            output_field=models.IntegerField()
        )
    )

def analyze_services(business, start_date, end_date):
    """Analyze service usage and performance"""
    services = AppointmentService.objects.filter(
        appointment__business=business,
        start_time__range=[start_date, end_date]
    )

    return services.values(
        'service__name'
    ).annotate(
        total_bookings=Count('id'),
        completed_bookings=Count(
            'id',
            filter=models.Q(appointment__status='COMPLETED')
        ),
        total_revenue=Sum('price'),
        avg_price=Avg('price')
    )

def analyze_revenue(business, start_date, end_date):
    """Analyze revenue patterns"""
    services = AppointmentService.objects.filter(
        appointment__business=business,
        start_time__range=[start_date, end_date],
        appointment__status='COMPLETED'
    )

    return {
        'total_revenue': services.aggregate(total=Sum('price'))['total'] or 0,
        'by_day': services.annotate(
            day=models.functions.Extract('start_time', 'day')
        ).values('day').annotate(
            revenue=Sum('price')
        ),
        'by_service': services.values('service__name').annotate(
            revenue=Sum('price')
        ),
        'by_staff': services.values(
            'staff__email',
            'staff__first_name',
            'staff__last_name'
        ).annotate(
            revenue=Sum('price')
        )
    }

# Helper functions
def get_memory_usage():
    """Get current memory usage"""
    import psutil
    return psutil.Process().memory_info().rss / 1024 / 1024  # Convert to MB

def get_cpu_usage():
    """Get current CPU usage"""
    import psutil
    return psutil.Process().cpu_percent()

def get_query_count():
    """Get database query count"""
    from django.db import connection
    return len(connection.queries)

def get_cache_hits():
    """Get cache hit count"""
    from django.core.cache import cache
    return getattr(cache, '_hits', 0)

def get_cache_misses():
    """Get cache miss count"""
    from django.core.cache import cache
    return getattr(cache, '_misses', 0)