from rest_framework import serializers
from django.contrib.auth import authenticate
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django.core.validators import MinValueValidator, MaxValueValidator
from datetime import datetime, timedelta
from decimal import Decimal

from .models import (
    Business,
    Service,
    Appointment,
    Schedule,
    CustomUser,
    DailyAnalytics,
    AppointmentService,
    # Add any other models you're using in serializers
)

from .exceptions import (
    ValidationError,
    AuthenticationError,
    BusinessError,
    ResourceNotFoundError,
    AppointmentError,
    DoubleBookingError,
    OutsideBusinessHoursError,
    StaffUnavailableError,
    PastDateError,
    CancellationError
)

# For nested serialization handling
from rest_framework.exceptions import ErrorDetail
from collections import OrderedDict

# For type hints (optional but recommended)
from typing import Dict, List, Any, Optional, Union
class StaffSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()
    schedule_conflicts = serializers.SerializerMethodField()

    class Meta:
        model = CustomUser
        fields = [
            'id', 'email', 'first_name', 'last_name', 'full_name',
            'user_type', 'business', 'is_active', 'schedule_conflicts',
            'last_login'
        ]
        read_only_fields = ['user_type', 'last_login', 'schedule_conflicts']
        extra_kwargs = {
            'email': {
                'error_messages': {
                    'blank': _('Email address is required.'),
                    'invalid': _('Please provide a valid email address.'),
                    'unique': _('A user with this email already exists.')
                }
            },
            'first_name': {
                'error_messages': {
                    'blank': _('First name is required.'),
                    'max_length': _('First name is too long (max 30 characters).')
                }
            },
            'last_name': {
                'error_messages': {
                    'blank': _('Last name is required.'),
                    'max_length': _('Last name is too long (max 30 characters).')
                }
            }
        }

    def get_full_name(self, obj):
        return obj.get_full_name() or obj.email

    def get_schedule_conflicts(self, obj):
        if not obj.is_active or obj.user_type != 'STAFF':
            return None
        
        # Get upcoming conflicting appointments
        conflicts = AppointmentService.objects.filter(
            staff=obj,
            start_time__lt=timezone.now() + timezone.timedelta(days=7),  # Next 7 days
            appointment__status__in=['PENDING', 'CONFIRMED']
        ).order_by('start_time')
        
        return [{
            'date': conflict.start_time.date(),
            'time': conflict.start_time.time(),
            'service': conflict.service.name
        } for conflict in conflicts]

class BusinessManagerRegistrationSerializer(serializers.ModelSerializer):
    password = serializers.CharField(
        write_only=True,
        min_length=8,
        error_messages={
            'min_length': _('Password must be at least 8 characters long.')
        }
    )
    confirm_password = serializers.CharField(write_only=True)

    class Meta:
        model = CustomUser
        fields = [
            'email', 'password', 'confirm_password', 'first_name',
            'last_name', 'business'
        ]
        extra_kwargs = {
            'email': {'required': True},
            'first_name': {'required': True},
            'last_name': {'required': True},
            'business': {'required': True}
        }

    def validate(self, data):
        if data['password'] != data['confirm_password']:
            raise ValidationError({
                'confirm_password': _('Passwords do not match.')
            })
        
        # Additional password validation
        password = data['password']
        if not any(char.isdigit() for char in password):
            raise ValidationError({
                'password': _('Password must contain at least one number.')
            })
        if not any(char.isupper() for char in password):
            raise ValidationError({
                'password': _('Password must contain at least one uppercase letter.')
            })
            
        return data

    def create(self, validated_data):
        validated_data.pop('confirm_password')
        validated_data['user_type'] = 'BUSINESS_ADMIN'
        user = CustomUser.objects.create_user(**validated_data)
        return user

class StaffRegistrationSerializer(serializers.ModelSerializer):
    password = serializers.CharField(
        write_only=True,
        min_length=8,
        error_messages={
            'min_length': _('Password must be at least 8 characters long.')
        }
    )
    confirm_password = serializers.CharField(write_only=True)

    class Meta:
        model = CustomUser
        fields = [
            'email', 'password', 'confirm_password', 'first_name',
            'last_name'
        ]
        extra_kwargs = {
            'email': {'required': True},
            'first_name': {'required': True},
            'last_name': {'required': True}
        }

    def validate(self, data):
        if data['password'] != data['confirm_password']:
            raise ValidationError({
                'confirm_password': _('Passwords do not match.')
            })
        return data

    def create(self, validated_data):
        validated_data.pop('confirm_password')
        validated_data['user_type'] = 'STAFF'
        validated_data['business'] = self.context['business']
        return CustomUser.objects.create_user(**validated_data)

class UserLoginSerializer(serializers.Serializer):
    email = serializers.EmailField(
        error_messages={
            'blank': _('Email address is required.'),
            'invalid': _('Please provide a valid email address.')
        }
    )
    password = serializers.CharField(
        write_only=True,
        error_messages={
            'blank': _('Password is required.')
        }
    )
    user_type = serializers.CharField(read_only=True)

    def validate(self, data):
        user = authenticate(email=data['email'], password=data['password'])
        if not user:
            raise AuthenticationError(_('Invalid email or password.'))
        if not user.is_active:
            raise AuthenticationError(_('This account has been disabled.'))
        if user.user_type not in ['SYSTEM_ADMIN', 'BUSINESS_ADMIN', 'STAFF']:
            raise AuthenticationError(_('Invalid account type.'))
        return user

class BusinessSerializer(serializers.ModelSerializer):
    staff_count = serializers.IntegerField(read_only=True)
    active_services = serializers.IntegerField(read_only=True)

    class Meta:
        model = Business
        fields = [
            'id', 'name', 'address', 'phone', 'created_at',
            'staff_count', 'active_services'
        ]
        read_only_fields = ['created_at']
        extra_kwargs = {
            'name': {
                'error_messages': {
                    'blank': _('Business name is required.'),
                    'max_length': _('Name is too long (max 100 characters).')
                }
            },
            'phone': {
                'error_messages': {
                    'blank': _('Phone number is required.'),
                    'invalid': _('Please provide a valid phone number.')
                }
            },
            'address': {
                'error_messages': {
                    'blank': _('Address is required.')
                }
            }
        }

class ServiceSerializer(serializers.ModelSerializer):
    duration_display = serializers.SerializerMethodField()
    appointment_count = serializers.IntegerField(read_only=True)
    
    class Meta:
        model = Service
        fields = [
            'id', 'name', 'duration', 'duration_display', 'price',
            'price_type', 'color', 'description', 'created_at',
            'updated_at', 'appointment_count'
        ]
        read_only_fields = ['created_at', 'updated_at', 'appointment_count']
        extra_kwargs = {
            'name': {
                'error_messages': {
                    'blank': _('Service name is required.'),
                    'max_length': _('Name is too long (max 100 characters).')
                }
            },
            'duration': {
                'error_messages': {
                    'invalid': _('Please provide a valid duration.')
                }
            },
            'price': {
                'error_messages': {
                    'invalid': _('Please provide a valid price.'),
                    'min_value': _('Price cannot be negative.')
                }
            }
        }

    def get_duration_display(self, obj):
        hours, remainder = divmod(obj.duration.seconds, 3600)
        minutes = remainder // 60
        parts = []
        if hours:
            parts.append(f"{hours}h")
        if minutes:
            parts.append(f"{minutes:02d}min")
        return " ".join(parts)

    def validate_duration(self, value):
        if value.total_seconds() < 900:  # 15 minutes
            raise ValidationError(_('Duration must be at least 15 minutes.'))
        if value.total_seconds() > 28800:  # 8 hours
            raise ValidationError(_('Duration cannot exceed 8 hours.'))
        return value

class AppointmentServiceSerializer(serializers.ModelSerializer):
    service_name = serializers.CharField(source='service.name', read_only=True)
    staff_name = serializers.CharField(source='staff.get_full_name', read_only=True)
    formatted_time = serializers.SerializerMethodField()

    class Meta:
        model = AppointmentService
        fields = [
            'id', 'service', 'service_name', 'staff', 'staff_name',
            'start_time', 'end_time', 'price', 'formatted_time'
        ]
        read_only_fields = ['price', 'end_time']
        extra_kwargs = {
            'service': {
                'error_messages': {
                    'null': _('Please select a service.'),
                    'does_not_exist': _('The selected service is not available.')
                }
            },
            'staff': {
                'error_messages': {
                    'null': _('Please select a staff member.'),
                    'does_not_exist': _('The selected staff member is not available.')
                }
            },
            'start_time': {
                'error_messages': {
                    'null': _('Please select an appointment time.'),
                    'invalid': _('Invalid appointment time format.')
                }
            }
        }

    def get_formatted_time(self, obj):
        return f"{obj.start_time.strftime('%I:%M %p')} - {obj.end_time.strftime('%I:%M %p')}"

    def validate(self, data):
        if 'start_time' in data and 'service' in data:
            # Calculate end time based on service duration
            data['end_time'] = data['start_time'] + data['service'].duration
            data['price'] = data['service'].price

            # Validate business hours
            if not self._is_within_business_hours(data['start_time'], data['end_time']):
                raise ValidationError(_('Selected time is outside business hours.'))

            # Validate staff availability
            if not self._is_staff_available(data):
                raise ValidationError(_('Selected staff is not available at this time.'))

        return data

    def _is_within_business_hours(self, start_time, end_time):
        schedule = Schedule.objects.filter(
            staff=self.initial_data['staff'],
            date=start_time.date(),
            start_time__lte=start_time.time(),
            end_time__gte=end_time.time()
        ).exists()
        return schedule

    def _is_staff_available(self, data):
        overlapping = AppointmentService.objects.filter(
            staff=data['staff'],
            start_time__lt=data['end_time'],
            end_time__gt=data['start_time'],
            appointment__status__in=['PENDING', 'CONFIRMED', 'IN_PROGRESS']
        )
        
        # Exclude current instance in case of updates
        if self.instance:
            overlapping = overlapping.exclude(pk=self.instance.pk)
            
        return not overlapping.exists()

class AppointmentSerializer(serializers.ModelSerializer):
    services = AppointmentServiceSerializer(many=True)
    total_duration = serializers.SerializerMethodField()
    formatted_status = serializers.SerializerMethodField()
    
    class Meta:
        model = Appointment
        fields = [
            'id', 'business', 'client_name', 'client_phone', 'status',
            'formatted_status', 'services', 'notes', 'total_price',
            'total_duration', 'created_at', 'updated_at'
        ]
        read_only_fields = ['status', 'total_price', 'created_at', 'updated_at']
        extra_kwargs = {
            'client_name': {
                'error_messages': {
                    'blank': _('Please provide your name.'),
                    'max_length': _('Name is too long (max 100 characters).')
                }
            },
            'client_phone': {
                'error_messages': {
                    'blank': _('Please provide your phone number.'),
                    'invalid': _('Please provide a valid phone number.')
                }
            }
        }

    def get_total_duration(self, obj):
        total_minutes = sum(
            (service.end_time - service.start_time).total_seconds() / 60
            for service in obj.services.all()
        )
        hours, minutes = divmod(int(total_minutes), 60)
        parts = []
        if hours:
            parts.append(f"{hours}h")
        if minutes:
            parts.append(f"{minutes}min")
        return " ".join(parts)

    def get_formatted_status(self, obj):
        return obj.get_status_display()

    def validate_services(self, services):
        if not services:
            raise ValidationError(_('At least one service is required.'))
        
        # Check for chronological order
        sorted_services = sorted(services, key=lambda x: x['start_time'])
        for i in range(len(sorted_services) - 1):
            if sorted_services[i]['end_time'] > sorted_services[i + 1]['start_time']:
                raise ValidationError(_('Services cannot overlap.'))
                
        return services

    def validate(self, data):
        if 'services' in data:
            # Check if all services are from the same business
            business = data.get('business') or self.instance.business
            for service_data in data['services']:
                if service_data['service'].business != business:
                    raise ValidationError(_('All services must be from the same business.'))

        return data

    def create(self, validated_data):
        services_data = validated_data.pop('services')
        appointment = Appointment.objects.create(**validated_data)
        
        for service_data in services_data:
            AppointmentService.objects.create(
                appointment=appointment,
                **service_data
            )
        
        appointment.total_price = appointment.calculate_total_price()
        appointment.save()
        
        return appointment

    def update(self, instance, validated_data):
        services_data = validated_data.pop('services', None)
        
        # Update appointment fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
            
        if services_data is not None:
            # Remove existing services
            instance.services.all().delete()
            
            # Create new services
            for service_data in services_data:
                AppointmentService.objects.create(
                    appointment=instance,
                    **service_data
                )
            
            # Update total price
            instance.total_price = instance.calculate_total_price()
            
        instance.save()
        return instance
class ScheduleSerializer(serializers.ModelSerializer):
    staff_name = serializers.CharField(source='staff.get_full_name', read_only=True)
    formatted_time = serializers.SerializerMethodField()
    appointment_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Schedule
        fields = [
            'id', 'business', 'staff', 'staff_name', 'date',
            'start_time', 'end_time', 'formatted_time', 'appointment_count'
        ]
        extra_kwargs = {
            'date': {
                'error_messages': {
                    'null': _('Please select a date.'),
                    'invalid': _('Invalid date format.')
                }
            },
            'start_time': {
                'error_messages': {
                    'null': _('Please select a start time.'),
                    'invalid': _('Invalid time format.')
                }
            },
            'end_time': {
                'error_messages': {
                    'null': _('Please select an end time.'),
                    'invalid': _('Invalid time format.')
                }
            }
        }

    def get_formatted_time(self, obj):
        return f"{obj.start_time.strftime('%I:%M %p')} - {obj.end_time.strftime('%I:%M %p')}"

    def validate(self, data):
        if data['start_time'] >= data['end_time']:
            raise ValidationError(_('End time must be after start time.'))

        # Check if date is in the past
        if data['date'] < timezone.now().date():
            raise ValidationError(_('Cannot create schedule for past dates.'))

        # Check for overlapping schedules
        overlapping = Schedule.objects.filter(
            staff=data['staff'],
            date=data['date'],
            start_time__lt=data['end_time'],
            end_time__gt=data['start_time']
        )
        
        if self.instance:
            overlapping = overlapping.exclude(pk=self.instance.pk)
            
        if overlapping.exists():
            raise ValidationError(_('This schedule overlaps with another schedule for this staff member.'))

        return data

class DailyAnalyticsSerializer(serializers.ModelSerializer):
    revenue_per_appointment = serializers.SerializerMethodField()
    cancellation_rate = serializers.SerializerMethodField()
    avg_service_duration_display = serializers.SerializerMethodField()

    class Meta:
        model = DailyAnalytics
        fields = [
            'id', 'business', 'date', 'total_appointments',
            'cancellations', 'total_revenue', 'avg_service_duration',
            'avg_service_duration_display', 'revenue_per_appointment',
            'cancellation_rate'
        ]
        read_only_fields = [
            'total_revenue', 'avg_service_duration', 'revenue_per_appointment',
            'cancellation_rate'
        ]

    def get_revenue_per_appointment(self, obj):
        if obj.total_appointments - obj.cancellations > 0:
            return round(obj.total_revenue / (obj.total_appointments - obj.cancellations), 2)
        return 0

    def get_cancellation_rate(self, obj):
        if obj.total_appointments > 0:
            return round((obj.cancellations / obj.total_appointments) * 100, 1)
        return 0

    def get_avg_service_duration_display(self, obj):
        if not obj.avg_service_duration:
            return "N/A"
        
        hours = obj.avg_service_duration.total_seconds() // 3600
        minutes = (obj.avg_service_duration.total_seconds() % 3600) // 60
        
        parts = []
        if hours:
            parts.append(f"{int(hours)}h")
        if minutes:
            parts.append(f"{int(minutes)}min")
        return " ".join(parts) if parts else "0min"

class BusinessAnalyticsSerializer(serializers.Serializer):
    start_date = serializers.DateField()
    end_date = serializers.DateField()
    total_appointments = serializers.IntegerField()
    total_revenue = serializers.DecimalField(max_digits=10, decimal_places=2)
    cancellation_rate = serializers.FloatField()
    average_appointment_value = serializers.DecimalField(max_digits=10, decimal_places=2)
    revenue_by_service = serializers.DictField(child=serializers.DecimalField(max_digits=10, decimal_places=2))
    revenue_by_staff = serializers.DictField(child=serializers.DecimalField(max_digits=10, decimal_places=2))
    appointments_by_day = serializers.DictField(child=serializers.IntegerField())
    busiest_hours = serializers.ListField(child=serializers.DictField())

    def validate(self, data):
        if data['start_date'] > data['end_date']:
            raise ValidationError(_('Start date must be before end date.'))
        
        if data['end_date'] > timezone.now().date():
            raise ValidationError(_('End date cannot be in the future.'))
        
        if (data['end_date'] - data['start_date']).days > 365:
            raise ValidationError(_('Date range cannot exceed one year.'))
            
        return data

class StaffPerformanceSerializer(serializers.Serializer):
    staff_member = serializers.DictField()
    total_appointments = serializers.IntegerField()
    completed_appointments = serializers.IntegerField()
    cancelled_appointments = serializers.IntegerField()
    total_revenue = serializers.DecimalField(max_digits=10, decimal_places=2)
    average_rating = serializers.FloatField()
    service_distribution = serializers.DictField()
    customer_feedback = serializers.ListField()

    def validate(self, data):
        if data['total_appointments'] < 0:
            raise ValidationError(_('Total appointments cannot be negative.'))
        
        if data['completed_appointments'] > data['total_appointments']:
            raise ValidationError(_('Completed appointments cannot exceed total appointments.'))
        
        if data['cancelled_appointments'] > data['total_appointments']:
            raise ValidationError(_('Cancelled appointments cannot exceed total appointments.'))
            
        return data

class NotificationSettingsSerializer(serializers.Serializer):
    email_notifications = serializers.BooleanField()
    sms_notifications = serializers.BooleanField()
    appointment_reminders = serializers.BooleanField()
    reminder_time = serializers.IntegerField(min_value=0, max_value=72)
    marketing_notifications = serializers.BooleanField()
    
    def validate_reminder_time(self, value):
        if value not in [24, 48, 72]:
            raise ValidationError(_('Reminder time must be 24, 48, or 72 hours.'))
        return value

class AppointmentRescheduleSerializer(serializers.Serializer):
    appointment_id = serializers.IntegerField()
    new_start_time = serializers.DateTimeField()
    reason = serializers.CharField(required=False, max_length=500)

    def validate(self, data):
        try:
            appointment = Appointment.objects.get(id=data['appointment_id'])
        except Appointment.DoesNotExist:
            raise ValidationError(_('Appointment not found.'))

        if appointment.status in ['COMPLETED', 'CANCELLED']:
            raise ValidationError(_('Cannot reschedule completed or cancelled appointments.'))

        if data['new_start_time'] < timezone.now():
            raise ValidationError(_('Cannot reschedule to a past time.'))

        return data