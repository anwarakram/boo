from django.contrib.admin.views.decorators import staff_member_required
from django.utils.decorators import method_decorator
from django.views.generic import TemplateView, View
from django.shortcuts import render
from django.http import JsonResponse
from django.utils import timezone
from django.db.models import Count, Avg, Sum
from datetime import datetime, timedelta
from .logging_system import AuditLog, ErrorLog
from .models import (
    Appointment, AppointmentService, Business, 
    CustomUser, DailyAnalytics
)

@method_decorator(staff_member_required, name='dispatch')
class LogViewerView(TemplateView):
    template_name = 'admin/log_viewer.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Get date range for filtering
        end_date = timezone.now()
        start_date = end_date - timedelta(days=7)  # Default to last 7 days
        
        if self.request.GET.get('start_date'):
            try:
                start_date = datetime.strptime(
                    self.request.GET['start_date'], 
                    '%Y-%m-%d'
                ).replace(tzinfo=timezone.utc)
            except ValueError:
                pass
                
        if self.request.GET.get('end_date'):
            try:
                end_date = datetime.strptime(
                    self.request.GET['end_date'], 
                    '%Y-%m-%d'
                ).replace(tzinfo=timezone.utc)
            except ValueError:
                pass

        # Get database logs
        audit_logs = AuditLog.objects.filter(
            timestamp__range=[start_date, end_date]
        ).order_by('-timestamp')
        
        error_logs = ErrorLog.objects.filter(
            timestamp__range=[start_date, end_date]
        ).order_by('-timestamp')
        
        # Get statistics
        audit_stats = {
            'total': audit_logs.count(),
            'by_action': dict(
                audit_logs.values_list('action').annotate(
                    count=Count('id')
                )
            ),
            'by_user': dict(
                audit_logs.values_list('user__email').annotate(
                    count=Count('id')
                )
            )
        }
        
        error_stats = {
            'total': error_logs.count(),
            'by_severity': dict(
                error_logs.values_list('severity').annotate(
                    count=Count('id')
                )
            ),
            'by_type': dict(
                error_logs.values_list('error_type').annotate(
                    count=Count('id')
                )
            )
        }
        
        context.update({
            'audit_logs': audit_logs[:100],  # Limit to last 100
            'error_logs': error_logs[:100],  # Limit to last 100
            'audit_stats': audit_stats,
            'error_stats': error_stats,
            'start_date': start_date.date(),
            'end_date': end_date.date(),
            'title': 'System Logs',
        })
        
        return context

class BusinessAnalyticsView(View):
    def get(self, request, business_id=None):
        if not request.user.is_authenticated or request.user.user_type not in ['SYSTEM_ADMIN', 'BUSINESS_ADMIN']:
            return JsonResponse({'error': 'Unauthorized'}, status=403)

        if business_id:
            if request.user.user_type == 'BUSINESS_ADMIN' and request.user.business.id != business_id:
                return JsonResponse({'error': 'Unauthorized'}, status=403)
            businesses = Business.objects.filter(id=business_id)
        else:
            if request.user.user_type == 'BUSINESS_ADMIN':
                businesses = Business.objects.filter(id=request.user.business.id)
            else:
                businesses = Business.objects.all()

        end_date = timezone.now().date()
        start_date = end_date - timedelta(days=30)

        analytics_data = {}
        for business in businesses:
            appointments = Appointment.objects.filter(
                business=business,
                created_at__date__range=[start_date, end_date]
            )
            
            services = AppointmentService.objects.filter(
                appointment__business=business,
                appointment__created_at__date__range=[start_date, end_date]
            )

            # Staff performance analysis
            staff_performance = services.values(
                'staff__email',
                'staff__first_name',
                'staff__last_name'
            ).annotate(
                total_appointments=Count('id'),
                total_revenue=Sum('price'),
            ).order_by('-total_appointments')

            # Service popularity analysis
            service_analysis = services.values(
                'service__name'
            ).annotate(
                total_bookings=Count('id'),
                total_revenue=Sum('price')
            ).order_by('-total_bookings')

            analytics_data[business.id] = {
                'name': business.name,
                'metrics': {
                    'total_appointments': appointments.count(),
                    'total_revenue': services.aggregate(Sum('price'))['price__sum'] or 0,
                    'cancellations': appointments.filter(status='CANCELLED').count(),
                    'completed': appointments.filter(status='COMPLETED').count()
                },
                'staff_performance': list(staff_performance),
                'service_analysis': list(service_analysis),
                'daily_stats': self._get_daily_stats(business, start_date, end_date)
            }

        return JsonResponse({
            'start_date': start_date.isoformat(),
            'end_date': end_date.isoformat(),
            'analytics': analytics_data
        })

    def _get_daily_stats(self, business, start_date, end_date):
        daily_stats = DailyAnalytics.objects.filter(
            business=business,
            date__range=[start_date, end_date]
        ).values(
            'date',
            'total_appointments',
            'cancellations',
            'total_revenue'
        ).order_by('date')
        
        return list(daily_stats)

@method_decorator(staff_member_required, name='dispatch')
class StaffPerformanceView(View):
    def get(self, request, staff_id=None):
        if not request.user.is_authenticated or request.user.user_type not in ['SYSTEM_ADMIN', 'BUSINESS_ADMIN']:
            return JsonResponse({'error': 'Unauthorized'}, status=403)

        end_date = timezone.now().date()
        start_date = end_date - timedelta(days=30)
        
        if staff_id:
            staff = CustomUser.objects.get(id=staff_id, user_type='STAFF')
            if request.user.user_type == 'BUSINESS_ADMIN' and staff.business != request.user.business:
                return JsonResponse({'error': 'Unauthorized'}, status=403)
                
            services = AppointmentService.objects.filter(
                staff=staff,
                start_time__date__range=[start_date, end_date]
            )
        else:
            if request.user.user_type == 'BUSINESS_ADMIN':
                services = AppointmentService.objects.filter(
                    staff__business=request.user.business,
                    start_time__date__range=[start_date, end_date]
                )
            else:
                services = AppointmentService.objects.filter(
                    start_time__date__range=[start_date, end_date]
                )

        performance_data = services.values(
            'staff__id',
            'staff__email',
            'staff__first_name',
            'staff__last_name'
        ).annotate(
            total_appointments=Count('id'),
            completed_appointments=Count(
                'id',
                filter={'appointment__status': 'COMPLETED'}
            ),
            total_revenue=Sum('price'),
            cancellations=Count(
                'id',
                filter={'appointment__status': 'CANCELLED'}
            )
        ).order_by('-total_appointments')

        return JsonResponse({
            'start_date': start_date.isoformat(),
            'end_date': end_date.isoformat(),
            'performance_data': list(performance_data)
        })