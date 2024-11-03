from django.db import transaction
from django.core.exceptions import ValidationError
from django.utils import timezone
from datetime import datetime, timedelta
from ..models import (
    Appointment, AppointmentService, Schedule, 
    Business, Service
)
from ..logging_system import LoggingService

class BookingManager:
    @staticmethod
    def validate_appointment_time(staff, start_time, end_time, exclude_appointment_id=None):
        """
        Validates if the appointment time is available
        Returns (bool, str) tuple indicating if valid and any error message
        """
        # Check if time is in the past
        if start_time < timezone.now():
            return False, "Cannot book appointments in the past"

        # Check staff schedule
        schedule = Schedule.objects.filter(
            staff=staff,
            date=start_time.date(),
            start_time__lte=start_time.time(),
            end_time__gte=end_time.time()
        ).first()
        
        if not schedule:
            return False, "Selected time is outside of staff working hours"

        # Check for overlapping appointments
        overlapping = AppointmentService.objects.filter(
            staff=staff,
            start_time__lt=end_time,
            end_time__gt=start_time,
            appointment__status__in=['PENDING', 'CONFIRMED', 'IN_PROGRESS']
        )

        if exclude_appointment_id:
            overlapping = overlapping.exclude(appointment_id=exclude_appointment_id)

        if overlapping.exists():
            return False, "Time slot conflicts with existing appointment"

        return True, None

    @staticmethod
    def get_available_slots(staff, date, service):
        """
        Returns available time slots for a given staff member and date
        """
        # Get staff schedule for the date
        schedule = Schedule.objects.filter(
            staff=staff,
            date=date
        ).first()

        if not schedule:
            return []

        # Get existing appointments
        existing_appointments = AppointmentService.objects.filter(
            staff=staff,
            start_time__date=date,
            appointment__status__in=['PENDING', 'CONFIRMED', 'IN_PROGRESS']
        ).order_by('start_time')

        available_slots = []
        current_time = timezone.make_aware(datetime.combine(date, schedule.start_time))
        end_time = timezone.make_aware(datetime.combine(date, schedule.end_time))

        # Create time slots
        while current_time + service.duration <= end_time:
            slot_end = current_time + service.duration
            
            # Check if slot conflicts with any existing appointment
            is_available = not any(
                appt.start_time < slot_end and appt.end_time > current_time
                for appt in existing_appointments
            )

            if is_available:
                available_slots.append({
                    'start_time': current_time,
                    'end_time': slot_end,
                    'formatted_time': f"{current_time.strftime('%I:%M %p')} - {slot_end.strftime('%I:%M %p')}"
                })

            current_time += timedelta(minutes=30)  # 30-minute intervals

        return available_slots

    @staticmethod
    @transaction.atomic
    def create_appointment(business, staff, service, start_time, client_name, 
                         client_phone, notes=None):
        """
        Creates an appointment with validation
        """
        end_time = start_time + service.duration

        # Validate time slot
        is_valid, error_message = BookingManager.validate_appointment_time(
            staff=staff,
            start_time=start_time,
            end_time=end_time
        )
        
        if not is_valid:
            raise ValidationError(error_message)

        # Create appointment
        appointment = Appointment.objects.create(
            business=business,
            client_name=client_name,
            client_phone=client_phone,
            status='PENDING',
            notes=notes
        )

        # Create appointment service
        AppointmentService.objects.create(
            appointment=appointment,
            service=service,
            staff=staff,
            start_time=start_time,
            end_time=end_time,
            price=service.price
        )

        LoggingService.log_action(
            user=staff,
            action='CREATE',
            content_object=appointment,
            details={
                'service': service.name,
                'start_time': start_time.isoformat(),
                'client_name': client_name
            }
        )

        return appointment

    @staticmethod
    def change_appointment_status(appointment, new_status, staff):
        """
        Change appointment status with proper validation and logging
        """
        if appointment.status == 'COMPLETED':
            raise ValidationError("Cannot modify completed appointments")

        old_status = appointment.status
        appointment.status = new_status
        appointment.save()

        LoggingService.log_action(
            user=staff,
            action='STATUS_CHANGE',
            content_object=appointment,
            details={
                'old_status': old_status,
                'new_status': new_status
            }
        )

        return appointment

    @staticmethod
    def reschedule_appointment(appointment, new_start_time, staff):
        """
        Reschedule an appointment with validation
        """
        if appointment.status in ['COMPLETED', 'CANCELLED']:
            raise ValidationError("Cannot reschedule completed or cancelled appointments")

        service = appointment.services.first().service
        new_end_time = new_start_time + service.duration

        # Validate new time slot
        is_valid, error_message = BookingManager.validate_appointment_time(
            staff=staff,
            start_time=new_start_time,
            end_time=new_end_time,
            exclude_appointment_id=appointment.id
        )

        if not is_valid:
            raise ValidationError(error_message)

        # Update appointment service times
        appointment_service = appointment.services.first()
        appointment_service.start_time = new_start_time
        appointment_service.end_time = new_end_time
        appointment_service.save()

        LoggingService.log_action(
            user=staff,
            action='RESCHEDULE',
            content_object=appointment,
            details={
                'old_time': appointment_service.start_time.isoformat(),
                'new_time': new_start_time.isoformat()
            }
        )

        return appointment

    @staticmethod
    def get_staff_schedule(staff, start_date, end_date):
        """
        Get staff schedule with appointments for a date range
        """
        schedules = Schedule.objects.filter(
            staff=staff,
            date__range=[start_date, end_date]
        ).order_by('date', 'start_time')

        appointments = AppointmentService.objects.filter(
            staff=staff,
            start_time__date__range=[start_date, end_date]
        ).select_related(
            'appointment',
            'service'
        ).order_by('start_time')

        return {
            'schedules': schedules,
            'appointments': appointments
        }