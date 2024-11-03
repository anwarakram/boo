from rest_framework import viewsets, filters, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import PermissionDenied
from rest_framework.authtoken.models import Token
from rest_framework.pagination import PageNumberPagination
from django_filters.rest_framework import DjangoFilterBackend
from django.contrib.auth import authenticate
from django.utils import timezone
from django.db.models import Q, Avg, Count, Sum, F
from django.db.models.functions import TruncDate, TruncWeek, TruncMonth, ExtractDay, ExtractHour
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils.translation import gettext_lazy as _
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional

from .models import (
    Business, Service, Appointment, Schedule, 
    CustomUser, DailyAnalytics, AppointmentService
)
from .serializers import (
    BusinessSerializer, ServiceSerializer, AppointmentSerializer, 
    ScheduleSerializer, StaffSerializer, BusinessManagerRegistrationSerializer, 
    StaffRegistrationSerializer, UserLoginSerializer, AppointmentServiceSerializer,
    DailyAnalyticsSerializer, BusinessAnalyticsSerializer, StaffPerformanceSerializer,
    NotificationSettingsSerializer, AppointmentRescheduleSerializer
)
from .permissions import (
    IsBusinessAdminOrSystemAdmin,
    IsStaffOrBusinessAdminOrSystemAdmin,
    IsBusinessAdmin,
    IsStaff,
    HasBusinessAccess,
    CanManageStaff,
    CanManageAppointments,
    CanViewAnalytics
)
from .exceptions import (
    ValidationError, AuthenticationError, BusinessError,
    ResourceNotFoundError, AppointmentError, DoubleBookingError,
    OutsideBusinessHoursError, StaffUnavailableError, PastDateError,
    CancellationError
)
from .logging_system import LoggingService
class CustomPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 100

    def get_paginated_response(self, data):
        return Response({
            'count': self.page.paginator.count,
            'next': self.get_next_link(),
            'previous': self.get_previous_link(),
            'current_page': self.page.number,
            'total_pages': self.page.paginator.num_pages,
            'results': data
        })

class AuthViewSet(viewsets.ViewSet):
    permission_classes = [permissions.AllowAny]

    @action(detail=False, methods=['post'])
    def business_register(self, request):
        """Register a new business manager"""
        try:
            serializer = BusinessManagerRegistrationSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            user = serializer.save()
            
            # Create authentication token
            token, _ = Token.objects.get_or_create(user=user)
            
            LoggingService.log_action(
                user=user,
                action='REGISTRATION',
                ip_address=request.META.get('REMOTE_ADDR'),
                details={'business_name': user.business.name}
            )
            
            return Response({
                'token': token.key,
                'user_type': user.user_type,
                'email': user.email,
                'business_id': user.business.id
            }, status=status.HTTP_201_CREATED)
            
        except ValidationError as e:
            return Response({'errors': e.detail}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            LoggingService.log_error(error=e, severity='ERROR', endpoint='business_register')
            raise

    @action(detail=False, methods=['post'])
    def staff_register(self, request):
        """Register new staff member (Business Admin only)"""
        if not request.user.is_authenticated or request.user.user_type != 'BUSINESS_ADMIN':
            raise PermissionDenied(_('Only business admins can register staff.'))
            
        try:
            serializer = StaffRegistrationSerializer(
                data=request.data,
                context={'business': request.user.business}
            )
            serializer.is_valid(raise_exception=True)
            user = serializer.save()
            
            LoggingService.log_action(
                user=request.user,
                action='STAFF_REGISTRATION',
                content_object=user,
                details={'staff_email': user.email}
            )
            
            return Response({
                'email': user.email,
                'user_type': user.user_type,
                'id': user.id
            }, status=status.HTTP_201_CREATED)
            
        except ValidationError as e:
            return Response({'errors': e.detail}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            LoggingService.log_error(
                error=e,
                severity='ERROR',
                user=request.user,
                endpoint='staff_register'
            )
            raise

    @action(detail=False, methods=['post'])
    def login(self, request):
        """User login endpoint"""
        try:
            serializer = UserLoginSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            user = serializer.validated_data
            
            # Create or get token
            token, _ = Token.objects.get_or_create(user=user)
            
            # Update login info
            user.last_login_ip = request.META.get('REMOTE_ADDR')
            user.last_login_device = request.META.get('HTTP_USER_AGENT')
            user.save(update_fields=['last_login_ip', 'last_login_device'])
            
            LoggingService.log_action(
                user=user,
                action='LOGIN',
                ip_address=user.last_login_ip,
                user_agent=user.last_login_device
            )
            
            return Response({
                'token': token.key,
                'user_type': user.user_type,
                'email': user.email,
                'business_id': user.business.id if user.business else None,
                'user_id': user.id
            })
            
        except AuthenticationError as e:
            return Response({'error': str(e)}, status=status.HTTP_401_UNAUTHORIZED)
        except Exception as e:
            LoggingService.log_error(
                error=e,
                severity='ERROR',
                endpoint='login'
            )
            raise

class BusinessViewSet(viewsets.ModelViewSet):
    serializer_class = BusinessSerializer
    permission_classes = [IsBusinessAdminOrSystemAdmin]
    pagination_class = CustomPagination
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'address', 'phone']
    ordering_fields = ['name', 'created_at']

    def get_queryset(self):
        if self.request.user.user_type == 'SYSTEM_ADMIN':
            return Business.objects.all()
        return Business.objects.filter(id=self.request.user.business.id)

    def perform_create(self, serializer):
        try:
            business = serializer.save()
            LoggingService.log_action(
                user=self.request.user,
                action='CREATE',
                content_object=business,
                details={'business_name': business.name}
            )
        except Exception as e:
            LoggingService.log_error(
                error=e,
                severity='ERROR',
                user=self.request.user,
                endpoint='business_create'
            )
            raise

    def perform_update(self, serializer):
        try:
            business = serializer.save()
            LoggingService.log_action(
                user=self.request.user,
                action='UPDATE',
                content_object=business,
                details={'business_name': business.name}
            )
        except Exception as e:
            LoggingService.log_error(
                error=e,
                severity='ERROR',
                user=self.request.user,
                endpoint='business_update'
            )
            raise

    @action(detail=True, methods=['get'])
    def analytics(self, request, pk=None):
        """Get business analytics"""
        try:
            business = self.get_object()
            end_date = timezone.now().date()
            start_date = end_date - timedelta(days=30)
            
            appointments = Appointment.objects.filter(
                business=business,
                created_at__date__range=[start_date, end_date]
            )
            
            analytics_data = {
                'total_appointments': appointments.count(),
                'completed_appointments': appointments.filter(status='COMPLETED').count(),
                'cancelled_appointments': appointments.filter(status='CANCELLED').count(),
                'total_revenue': appointments.filter(
                    status='COMPLETED'
                ).aggregate(total=Sum('total_price'))['total'] or 0,
                'daily_stats': self._get_daily_stats(business, start_date, end_date),
                'service_stats': self._get_service_stats(business, start_date, end_date),
                'staff_stats': self._get_staff_stats(business, start_date, end_date)
            }
            
            return Response(analytics_data)
            
        except Exception as e:
            LoggingService.log_error(
                error=e,
                severity='ERROR',
                user=request.user,
                endpoint='business_analytics'
            )
            raise

    def _get_daily_stats(self, business, start_date, end_date):
        return DailyAnalytics.objects.filter(
            business=business,
            date__range=[start_date, end_date]
        ).values('date', 'total_appointments', 'total_revenue')

    def _get_service_stats(self, business, start_date, end_date):
        return AppointmentService.objects.filter(
            appointment__business=business,
            appointment__created_at__date__range=[start_date, end_date],
            appointment__status='COMPLETED'
        ).values(
            'service__name'
        ).annotate(
            count=Count('id'),
            revenue=Sum('price')
        )

    def _get_staff_stats(self, business, start_date, end_date):
        return AppointmentService.objects.filter(
            appointment__business=business,
            appointment__created_at__date__range=[start_date, end_date]
        ).values(
            'staff__email',
            'staff__first_name',
            'staff__last_name'
        ).annotate(
            total_appointments=Count('id'),
            completed_appointments=Count(
                'id',
                filter=Q(appointment__status='COMPLETED')
            ),
            revenue=Sum(
                'price',
                filter=Q(appointment__status='COMPLETED')
            )
        )

class ServiceViewSet(viewsets.ModelViewSet):
    serializer_class = ServiceSerializer
    permission_classes = [IsBusinessAdminOrSystemAdmin]
    pagination_class = CustomPagination
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'description']
    ordering_fields = ['name', 'price', 'duration']

    def get_queryset(self):
        return Service.objects.filter(
            business=self.request.user.business
        ).annotate(
            appointment_count=Count('appointmentservice')
        )

    def perform_create(self, serializer):
        try:
            service = serializer.save(business=self.request.user.business)
            LoggingService.log_action(
                user=self.request.user,
                action='CREATE',
                content_object=service,
                details={'service_name': service.name}
            )
        except Exception as e:
            LoggingService.log_error(
                error=e,
                severity='ERROR',
                user=self.request.user,
                endpoint='service_create'
            )
            raise

    @action(detail=True, methods=['get'])
    def availability(self, request, pk=None):
        """Get service availability for next 7 days"""
        try:
            service = self.get_object()
            start_date = timezone.now().date()
            end_date = start_date + timedelta(days=7)
            
            staff_members = CustomUser.objects.filter(
                business=service.business,
                user_type='STAFF',
                is_active=True
            )
            
            availability = {}
            for date in (start_date + timedelta(n) for n in range(8)):
                availability[date.isoformat()] = []
                
                for staff in staff_members:
                    schedule = Schedule.objects.filter(
                        staff=staff,
                        date=date
                    ).first()
                    
                    if schedule:
                        slots = self._get_available_slots(
                            staff,
                            schedule,
                            service,
                            date
                        )
                        if slots:
                            availability[date.isoformat()].append({
                                'staff_id': staff.id,
                                'staff_name': staff.get_full_name(),
                                'available_slots': slots
                            })
            
            return Response(availability)
            
        except Exception as e:
            LoggingService.log_error(
                error=e,
                severity='ERROR',
                user=request.user,
                endpoint='service_availability'
            )
            raise

    def _get_available_slots(self, staff, schedule, service, date):
        """Calculate available time slots for a staff member"""
        slots = []
        current_time = timezone.make_aware(
            datetime.combine(date, schedule.start_time)
        )
        end_time = timezone.make_aware(
            datetime.combine(date, schedule.end_time)
        )

        # Get existing appointments
        existing_appointments = AppointmentService.objects.filter(
            staff=staff,
            start_time__date=date,
            appointment__status__in=['PENDING', 'CONFIRMED', 'IN_PROGRESS']
        ).order_by('start_time')

        while current_time + service.duration <= end_time:
            slot_end = current_time + service.duration
            is_available = not existing_appointments.filter(
                start_time__lt=slot_end,
                end_time__gt=current_time
            ).exists()

            if is_available:
                slots.append({
                    'start_time': current_time.isoformat(),
                    'end_time': slot_end.isoformat(),
                })

            current_time += timedelta(minutes=30)

        return slots
class AppointmentViewSet(viewsets.ModelViewSet):
    permission_classes = [IsStaffOrBusinessAdminOrSystemAdmin]
    pagination_class = CustomPagination
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['status', 'services__staff']
    search_fields = ['client_name', 'client_phone', 'services__staff__first_name', 
                    'services__staff__last_name', 'services__service__name']
    ordering_fields = ['created_at', 'status', 'total_price']

    def get_serializer_class(self):
        if self.action == 'reschedule':
            return AppointmentRescheduleSerializer
        return AppointmentSerializer

    def get_queryset(self):
        queryset = Appointment.objects.filter(
            business=self.request.user.business
        ).prefetch_related(
            'services',
            'services__service',
            'services__staff'
        )

        # Filter by date range if provided
        start_date = self.request.query_params.get('start_date')
        end_date = self.request.query_params.get('end_date')
        if start_date and end_date:
            try:
                queryset = queryset.filter(
                    services__start_time__date__range=[start_date, end_date]
                )
            except ValidationError:
                raise ValidationError(_('Invalid date format. Use YYYY-MM-DD.'))

        return queryset.distinct()

    def perform_create(self, serializer):
        try:
            appointment = serializer.save(business=self.request.user.business)
            
            LoggingService.log_action(
                user=self.request.user,
                action='APPOINTMENT_CREATE',
                content_object=appointment,
                details={
                    'client_name': appointment.client_name,
                    'services': list(appointment.services.values_list('service__name', flat=True))
                }
            )
            
            # Send confirmation notifications
            self._send_appointment_notifications(appointment, 'created')
            
        except Exception as e:
            LoggingService.log_error(
                error=e,
                severity='ERROR',
                user=self.request.user,
                endpoint='appointment_create'
            )
            raise

    @action(detail=True, methods=['post'])
    def reschedule(self, request, pk=None):
        """Reschedule an appointment"""
        try:
            appointment = self.get_object()
            serializer = AppointmentRescheduleSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            
            new_start_time = serializer.validated_data['new_start_time']
            reason = serializer.validated_data.get('reason')
            
            # Validate new time
            if new_start_time < timezone.now():
                raise PastDateError()
                
            # Check staff availability
            services = appointment.services.all()
            for service in services:
                if not self._is_staff_available(service.staff, new_start_time, service.service.duration):
                    raise StaffUnavailableError()
            
            # Update appointment times
            time_difference = new_start_time - services[0].start_time
            for service in services:
                service.start_time += time_difference
                service.end_time += time_difference
                service.save()
            
            appointment.save()
            
            LoggingService.log_action(
                user=request.user,
                action='APPOINTMENT_RESCHEDULE',
                content_object=appointment,
                details={
                    'old_time': services[0].start_time.isoformat(),
                    'new_time': new_start_time.isoformat(),
                    'reason': reason
                }
            )
            
            # Send notifications
            self._send_appointment_notifications(appointment, 'rescheduled')
            
            return Response(self.get_serializer(appointment).data)
            
        except Exception as e:
            LoggingService.log_error(
                error=e,
                severity='ERROR',
                user=request.user,
                endpoint='appointment_reschedule'
            )
            raise

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """Cancel an appointment"""
        try:
            appointment = self.get_object()
            
            if appointment.status in ['COMPLETED', 'CANCELLED']:
                raise CancellationError(_('Cannot cancel completed or already cancelled appointments.'))
            
            reason = request.data.get('reason')
            appointment.status = 'CANCELLED'
            appointment.save()
            
            LoggingService.log_action(
                user=request.user,
                action='APPOINTMENT_CANCEL',
                content_object=appointment,
                details={'reason': reason}
            )
            
            # Send notifications
            self._send_appointment_notifications(appointment, 'cancelled')
            
            return Response(self.get_serializer(appointment).data)
            
        except Exception as e:
            LoggingService.log_error(
                error=e,
                severity='ERROR',
                user=request.user,
                endpoint='appointment_cancel'
            )
            raise

    @action(detail=True, methods=['post'])
    def complete(self, request, pk=None):
        """Mark appointment as completed"""
        try:
            appointment = self.get_object()
            
            if appointment.status != 'IN_PROGRESS':
                raise ValidationError(_('Only in-progress appointments can be completed.'))
            
            appointment.status = 'COMPLETED'
            appointment.save()
            
            LoggingService.log_action(
                user=request.user,
                action='APPOINTMENT_COMPLETE',
                content_object=appointment
            )
            
            # Update analytics
            self._update_analytics(appointment)
            
            return Response(self.get_serializer(appointment).data)
            
        except Exception as e:
            LoggingService.log_error(
                error=e,
                severity='ERROR',
                user=request.user,
                endpoint='appointment_complete'
            )
            raise

    @action(detail=False, methods=['get'])
    def available_slots(self, request):
        """Get available appointment slots"""
        try:
            staff_id = request.query_params.get('staff')
            service_id = request.query_params.get('service')
            date_str = request.query_params.get('date')
            
            if not all([staff_id, service_id, date_str]):
                raise ValidationError(_('staff, service and date are required parameters'))
                
            staff = CustomUser.objects.get(id=staff_id)
            service = Service.objects.get(id=service_id)
            date = datetime.strptime(date_str, '%Y-%m-%d').date()
            
            schedule = Schedule.objects.filter(
                staff=staff,
                date=date
            ).first()
            
            if not schedule:
                return Response({'slots': []})
                
            slots = self._calculate_available_slots(staff, service, schedule)
            return Response({'slots': slots})
            
        except Exception as e:
            LoggingService.log_error(
                error=e,
                severity='ERROR',
                user=request.user,
                endpoint='available_slots'
            )
            raise

    def _is_staff_available(self, staff, start_time, duration):
        """Check if staff is available for the given time slot"""
        end_time = start_time + duration
        
        # Check schedule
        schedule = Schedule.objects.filter(
            staff=staff,
            date=start_time.date(),
            start_time__lte=start_time.time(),
            end_time__gte=end_time.time()
        ).exists()
        
        if not schedule:
            return False
            
        # Check existing appointments
        conflicts = AppointmentService.objects.filter(
            staff=staff,
            start_time__lt=end_time,
            end_time__gt=start_time,
            appointment__status__in=['PENDING', 'CONFIRMED', 'IN_PROGRESS']
        ).exists()
        
        return not conflicts

    def _calculate_available_slots(self, staff, service, schedule):
        """Calculate available time slots"""
        slots = []
        current_time = timezone.make_aware(
            datetime.combine(schedule.date, schedule.start_time)
        )
        end_time = timezone.make_aware(
            datetime.combine(schedule.date, schedule.end_time)
        )
        
        while current_time + service.duration <= end_time:
            if self._is_staff_available(staff, current_time, service.duration):
                slots.append({
                    'start_time': current_time.isoformat(),
                    'end_time': (current_time + service.duration).isoformat(),
                })
            current_time += timedelta(minutes=30)
            
        return slots

    def _send_appointment_notifications(self, appointment, action):
        """Send notifications about appointment updates"""
        from .utils import send_appointment_notification  # Import here to avoid circular imports
        
        try:
            send_appointment_notification(
                appointment=appointment,
                action=action,
                user=self.request.user
            )
        except Exception as e:
            LoggingService.log_error(
                error=e,
                severity='WARNING',
                user=self.request.user,
                endpoint='appointment_notifications'
            )

    def _update_analytics(self, appointment):
        """Update analytics after appointment completion"""
        try:
            analytics, created = DailyAnalytics.objects.get_or_create(
                business=appointment.business,
                date=timezone.now().date()
            )
            
            analytics.total_appointments = F('total_appointments') + 1
            
            if appointment.status == 'COMPLETED':
                analytics.total_revenue = F('total_revenue') + appointment.total_price
                
            analytics.save()
            
        except Exception as e:
            LoggingService.log_error(
                error=e,
                severity='WARNING',
                user=self.request.user,
                endpoint='analytics_update'
            )
class ScheduleViewSet(viewsets.ModelViewSet):
    serializer_class = ScheduleSerializer
    permission_classes = [IsBusinessAdminOrSystemAdmin]
    pagination_class = CustomPagination
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['staff', 'date']
    ordering_fields = ['date', 'start_time']

    def get_queryset(self):
        queryset = Schedule.objects.filter(
            business=self.request.user.business
        ).select_related('staff').annotate(
            appointment_count=Count('staff__appointmentservice', 
                filter=Q(staff__appointmentservice__start_time__date=F('date')))
        )
        
        # Filter by date range if provided
        start_date = self.request.query_params.get('start_date')
        end_date = self.request.query_params.get('end_date')
        if start_date and end_date:
            try:
                queryset = queryset.filter(date__range=[start_date, end_date])
            except ValidationError:
                raise ValidationError(_('Invalid date format. Use YYYY-MM-DD.'))

        return queryset

    def perform_create(self, serializer):
        try:
            schedule = serializer.save(business=self.request.user.business)
            LoggingService.log_action(
                user=self.request.user,
                action='SCHEDULE_CREATE',
                content_object=schedule,
                details={
                    'staff': schedule.staff.get_full_name(),
                    'date': schedule.date.isoformat()
                }
            )
        except Exception as e:
            LoggingService.log_error(
                error=e,
                severity='ERROR',
                user=self.request.user,
                endpoint='schedule_create'
            )
            raise

    @action(detail=False, methods=['post'])
    def bulk_create(self, request):
        """Create multiple schedules at once"""
        try:
            schedules_data = request.data.get('schedules', [])
            if not schedules_data:
                raise ValidationError(_('No schedule data provided.'))

            created_schedules = []
            for schedule_data in schedules_data:
                serializer = self.get_serializer(data=schedule_data)
                serializer.is_valid(raise_exception=True)
                schedule = serializer.save(business=self.request.user.business)
                created_schedules.append(schedule)

            LoggingService.log_action(
                user=self.request.user,
                action='SCHEDULE_BULK_CREATE',
                details={'count': len(created_schedules)}
            )

            return Response(
                self.get_serializer(created_schedules, many=True).data,
                status=status.HTTP_201_CREATED
            )

        except Exception as e:
            LoggingService.log_error(
                error=e,
                severity='ERROR',
                user=self.request.user,
                endpoint='schedule_bulk_create'
            )
            raise

class StaffViewSet(viewsets.ModelViewSet):
    serializer_class = StaffSerializer
    permission_classes = [IsBusinessAdminOrSystemAdmin]
    pagination_class = CustomPagination
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['email', 'first_name', 'last_name']
    ordering_fields = ['email', 'first_name', 'last_name']

    def get_queryset(self):
        if self.request.user.user_type == 'SYSTEM_ADMIN':
            return CustomUser.objects.filter(user_type='STAFF')
        return CustomUser.objects.filter(
            user_type='STAFF',
            business=self.request.user.business
        )

    @action(detail=True, methods=['get'])
    def performance(self, request, pk=None):
        """Get staff member performance metrics"""
        try:
            staff = self.get_object()
            end_date = timezone.now().date()
            start_date = end_date - timedelta(days=30)
            
            if 'start_date' in request.query_params and 'end_date' in request.query_params:
                start_date = datetime.strptime(request.query_params['start_date'], '%Y-%m-%d').date()
                end_date = datetime.strptime(request.query_params['end_date'], '%Y-%m-%d').date()

            appointments = AppointmentService.objects.filter(
                staff=staff,
                start_time__date__range=[start_date, end_date]
            )

            performance_data = {
                'staff_member': {
                    'id': staff.id,
                    'name': staff.get_full_name(),
                    'email': staff.email
                },
                'total_appointments': appointments.count(),
                'completed_appointments': appointments.filter(
                    appointment__status='COMPLETED'
                ).count(),
                'cancelled_appointments': appointments.filter(
                    appointment__status='CANCELLED'
                ).count(),
                'total_revenue': appointments.filter(
                    appointment__status='COMPLETED'
                ).aggregate(total=Sum('price'))['total'] or 0,
                'service_distribution': self._get_service_distribution(appointments),
                'daily_stats': self._get_daily_stats(appointments),
                'average_rating': self._get_average_rating(staff)
            }

            return Response(performance_data)

        except Exception as e:
            LoggingService.log_error(
                error=e,
                severity='ERROR',
                user=request.user,
                endpoint='staff_performance'
            )
            raise

    def _get_service_distribution(self, appointments):
        return appointments.values(
            'service__name'
        ).annotate(
            count=Count('id'),
            revenue=Sum('price')
        ).order_by('-count')

    def _get_daily_stats(self, appointments):
        return appointments.annotate(
            date=TruncDate('start_time')
        ).values('date').annotate(
            appointments=Count('id'),
            completed=Count('id', filter=Q(appointment__status='COMPLETED')),
            revenue=Sum('price', filter=Q(appointment__status='COMPLETED'))
        ).order_by('date')

    def _get_average_rating(self, staff):
        # Implement your rating logic here
        return None

class BusinessAnalyticsView(APIView):
    permission_classes = [IsBusinessAdminOrSystemAdmin]

    def get(self, request, business_id=None):
        """Get comprehensive business analytics"""
        try:
            if business_id and request.user.user_type != 'SYSTEM_ADMIN':
                if request.user.business.id != business_id:
                    raise PermissionDenied()

            business = Business.objects.get(id=business_id or request.user.business.id)
            end_date = timezone.now().date()
            start_date = end_date - timedelta(days=30)

            if 'start_date' in request.query_params and 'end_date' in request.query_params:
                start_date = datetime.strptime(request.query_params['start_date'], '%Y-%m-%d').date()
                end_date = datetime.strptime(request.query_params['end_date'], '%Y-%m-%d').date()

            analytics_data = {
                'period': {
                    'start_date': start_date,
                    'end_date': end_date
                },
                'overview': self._get_overview(business, start_date, end_date),
                'revenue': self._get_revenue_analysis(business, start_date, end_date),
                'appointments': self._get_appointment_analysis(business, start_date, end_date),
                'services': self._get_service_analysis(business, start_date, end_date),
                'staff': self._get_staff_analysis(business, start_date, end_date),
                'customer': self._get_customer_analysis(business, start_date, end_date)
            }

            return Response(analytics_data)

        except Exception as e:
            LoggingService.log_error(
                error=e,
                severity='ERROR',
                user=request.user,
                endpoint='business_analytics'
            )
            raise

    def _get_overview(self, business, start_date, end_date):
        appointments = Appointment.objects.filter(
            business=business,
            created_at__date__range=[start_date, end_date]
        )
        
        total_revenue = appointments.filter(
            status='COMPLETED'
        ).aggregate(total=Sum('total_price'))['total'] or 0
        
        return {
            'total_appointments': appointments.count(),
            'completed_appointments': appointments.filter(status='COMPLETED').count(),
            'cancelled_appointments': appointments.filter(status='CANCELLED').count(),
            'total_revenue': total_revenue,
            'average_appointment_value': total_revenue / appointments.filter(
                status='COMPLETED'
            ).count() if appointments.filter(status='COMPLETED').exists() else 0
        }

    def _get_revenue_analysis(self, business, start_date, end_date):
        completed_appointments = Appointment.objects.filter(
            business=business,
            created_at__date__range=[start_date, end_date],
            status='COMPLETED'
        )
        
        return {
            'daily_revenue': completed_appointments.annotate(
                date=TruncDate('created_at')
            ).values('date').annotate(
                revenue=Sum('total_price')
            ).order_by('date'),
            'service_revenue': AppointmentService.objects.filter(
                appointment__business=business,
                appointment__created_at__date__range=[start_date, end_date],
                appointment__status='COMPLETED'
            ).values('service__name').annotate(
                revenue=Sum('price')
            ).order_by('-revenue'),
            'staff_revenue': AppointmentService.objects.filter(
                appointment__business=business,
                appointment__created_at__date__range=[start_date, end_date],
                appointment__status='COMPLETED'
            ).values(
                'staff__email',
                'staff__first_name',
                'staff__last_name'
            ).annotate(
                revenue=Sum('price')
            ).order_by('-revenue')
        }

    def _get_appointment_analysis(self, business, start_date, end_date):
        appointments = Appointment.objects.filter(
            business=business,
            created_at__date__range=[start_date, end_date]
        )
        
        return {
            'by_status': appointments.values(
                'status'
            ).annotate(
                count=Count('id')
            ),
            'by_day': appointments.annotate(
                day=ExtractDay('created_at')
            ).values('day').annotate(
                count=Count('id')
            ),
            'by_hour': appointments.annotate(
                hour=ExtractHour('created_at')
            ).values('hour').annotate(
                count=Count('id')
            ),
            'average_duration': appointments.filter(
                status='COMPLETED'
            ).aggregate(
                avg_duration=Avg(
                    F('services__end_time') - F('services__start_time')
                )
            )
        }

    def _get_service_analysis(self, business, start_date, end_date):
        services = AppointmentService.objects.filter(
            appointment__business=business,
            appointment__created_at__date__range=[start_date, end_date]
        )
        
        return {
            'popular_services': services.values(
                'service__name'
            ).annotate(
                count=Count('id')
            ).order_by('-count'),
            'service_completion_rate': services.values(
                'service__name'
            ).annotate(
                total=Count('id'),
                completed=Count(
                    'id',
                    filter=Q(appointment__status='COMPLETED')
                )
            ).annotate(
                completion_rate=F('completed') * 100.0 / F('total')
            )
        }

    def _get_staff_analysis(self, business, start_date, end_date):
        services = AppointmentService.objects.filter(
            appointment__business=business,
            appointment__created_at__date__range=[start_date, end_date]
        )
        
        return {
            'staff_performance': services.values(
                'staff__email',
                'staff__first_name',
                'staff__last_name'
            ).annotate(
                total_appointments=Count('id'),
                completed_appointments=Count(
                    'id',
                    filter=Q(appointment__status='COMPLETED')
                ),
                total_revenue=Sum(
                    'price',
                    filter=Q(appointment__status='COMPLETED')
                ),
                average_duration=Avg(
                    F('end_time') - F('start_time')
                )
            )
        }

    def _get_customer_analysis(self, business, start_date, end_date):
        appointments = Appointment.objects.filter(
            business=business,
            created_at__date__range=[start_date, end_date]
        )
        
        return {
            'new_customers': appointments.values(
                'client_phone'
            ).annotate(
                first_visit=Min('created_at')
            ).filter(
                first_visit__date__range=[start_date, end_date]
            ).count(),
            'returning_customers': appointments.values(
                'client_phone'
            ).annotate(
                visit_count=Count('id')
            ).filter(
                visit_count__gt=1
            ).count(),
            'top_customers': appointments.values(
                'client_name',
                'client_phone'
            ).annotate(
                visit_count=Count('id'),
                total_spent=Sum('total_price')
            ).order_by('-visit_count')[:10]
        }
