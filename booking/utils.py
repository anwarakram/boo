import logging
from datetime import datetime, timedelta
from django.utils import timezone
from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.db.models import Count, Avg
from django.db.models.functions import TruncDate
from .models import AppointmentService, Appointment, Schedule

# Configure logger
logger = logging.getLogger(__name__)

def get_available_slots(business, service, date, staff=None):
    """
    Get available appointment slots for a given service on a specific date
    
    Args:
        business: Business instance
        service: Service instance
        date: datetime.date instance
        staff: CustomUser instance (optional)
        
    Returns:
        list: Available time slots with staff members
    """
    try:
        # Convert date to datetime objects for start and end of day
        start_datetime = timezone.make_aware(datetime.combine(date, datetime.min.time()))
        end_datetime = timezone.make_aware(datetime.combine(date, datetime.max.time()))
        
        # Get staff schedules for the day
        schedules = Schedule.objects.filter(
            business=business,
            date=date,
            staff__is_active=True  # Only consider active staff
        )
        if staff:
            schedules = schedules.filter(staff=staff)
        
        # Get existing appointments
        existing_appointments = AppointmentService.objects.filter(
            appointment__business=business,
            start_time__gte=start_datetime,
            end_time__lte=end_datetime,
            appointment__status__in=['PENDING', 'CONFIRMED', 'IN_PROGRESS']  # Only consider active appointments
        )
        if staff:
            existing_appointments = existing_appointments.filter(staff=staff)
        
        available_slots = []
        
        for schedule in schedules:
            current_time = timezone.make_aware(datetime.combine(date, schedule.start_time))
            end_time = timezone.make_aware(datetime.combine(date, schedule.end_time))
            
            while current_time + service.duration <= end_time:
                slot_end_time = current_time + service.duration
                
                # Check if slot conflicts with existing appointments
                conflict = existing_appointments.filter(
                    staff=schedule.staff,
                    start_time__lt=slot_end_time,
                    end_time__gt=current_time
                ).exists()
                
                if not conflict:
                    available_slots.append({
                        'start_time': current_time,
                        'end_time': slot_end_time,
                        'staff': schedule.staff,
                        'staff_name': schedule.staff.get_full_name() or schedule.staff.email,
                        'formatted_time': format_time_slot(current_time, slot_end_time)
                    })
                
                current_time += timedelta(minutes=30)  # 30-minute intervals
        
        # Sort slots by time and then by staff name
        return sorted(available_slots, key=lambda x: (x['start_time'], x['staff_name']))
    
    except Exception as e:
        logger.error(f"Error in get_available_slots: {str(e)}")
        return []

def send_appointment_confirmation(appointment):
    """
    Send confirmation email for a new appointment
    """
    try:
        context = {
            'customer_name': appointment.customer.user.get_full_name() or appointment.customer.user.email,
            'business_name': appointment.business.name,
            'services': appointment.services.all().select_related('service', 'staff'),
            'total_price': f"IQD {appointment.total_price}",
            'status': appointment.get_status_display(),
            'appointment_id': appointment.id
        }
        
        subject = f'Appointment Confirmation - {appointment.business.name}'
        html_message = render_to_string('emails/appointment_confirmation.html', context)
        plain_message = render_to_string('emails/appointment_confirmation.txt', context)
        
        send_mail(
            subject=subject,
            message=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[appointment.customer.user.email],
            html_message=html_message,
            fail_silently=False
        )
        
        logger.info(f"Sent confirmation email for appointment {appointment.id}")
        return True
    except Exception as e:
        logger.error(f"Error sending appointment confirmation: {str(e)}")
        return False

def send_appointment_reminder(appointment):
    """
    Send reminder email for an upcoming appointment
    """
    try:
        first_service = appointment.services.all().order_by('start_time').first()
        if not first_service:
            logger.warning(f"No services found for appointment {appointment.id}")
            return False
            
        context = {
            'customer_name': appointment.customer.user.get_full_name() or appointment.customer.user.email,
            'business_name': appointment.business.name,
            'appointment_date': first_service.start_time.strftime("%B %d, %Y"),
            'appointment_time': first_service.start_time.strftime("%I:%M %p"),
            'services': appointment.services.all().select_related('service', 'staff'),
            'total_price': f"IQD {appointment.total_price}",
            'appointment_id': appointment.id,
            'business_address': appointment.business.address,
            'business_phone': appointment.business.phone
        }
        
        subject = f'Reminder: Your appointment at {appointment.business.name}'
        html_message = render_to_string('emails/appointment_reminder.html', context)
        plain_message = render_to_string('emails/appointment_reminder.txt', context)
        
        send_mail(
            subject=subject,
            message=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[appointment.customer.user.email],
            html_message=html_message,
            fail_silently=False
        )
        
        logger.info(f"Sent reminder email for appointment {appointment.id}")
        return True
    except Exception as e:
        logger.error(f"Error sending appointment reminder: {str(e)}")
        return False

def get_appointment_summary(appointment):
    """
    Get a summary of an appointment's details
    
    Args:
        appointment: Appointment instance
        
    Returns:
        dict: Appointment summary
    """
    try:
        services = appointment.services.all().select_related('service', 'staff')
        first_service = services.order_by('start_time').first()
        
        return {
            'id': appointment.id,
            'status': appointment.get_status_display(),
            'customer': {
                'name': appointment.customer.user.get_full_name() or appointment.customer.user.email,
                'phone': appointment.customer.phone
            },
            'date': first_service.start_time.strftime("%B %d, %Y") if first_service else None,
            'services': [{
                'name': service.service.name,
                'time': format_time_slot(service.start_time, service.end_time),
                'staff': service.staff.get_full_name() or service.staff.email,
                'price': f"IQD {service.price}"
            } for service in services],
            'total_price': f"IQD {appointment.total_price}",
            'reminder': f"{appointment.reminder_minutes} minutes before" if appointment.reminder_minutes else None
        }
    except Exception as e:
        logger.error(f"Error getting appointment summary: {str(e)}")
        return None

def calculate_business_metrics(business, start_date, end_date):
    """
    Calculate business metrics for a given date range
    
    Args:
        business: Business instance
        start_date: datetime.date
        end_date: datetime.date
        
    Returns:
        dict: Business metrics
    """
    try:
        appointments = Appointment.objects.filter(
            business=business,
            created_at__date__range=[start_date, end_date]
        )
        
        services = AppointmentService.objects.filter(
            appointment__business=business,
            start_time__date__range=[start_date, end_date]
        ).select_related('service', 'staff', 'appointment')
        
        # Calculate total revenue including only completed appointments
        completed_services = services.filter(appointment__status='COMPLETED')
        total_revenue = sum(service.price for service in completed_services)
        
        # Get staff performance metrics
        staff_metrics = services.values(
            'staff__id',
            'staff__email',
            'staff__first_name',
            'staff__last_name'
        ).annotate(
            total_appointments=Count('id'),
            completed_appointments=Count('id', filter={'appointment__status': 'COMPLETED'}),
            no_shows=Count('id', filter={'appointment__is_no_show': True})
        )
        
        return {
            'period': {
                'start_date': start_date,
                'end_date': end_date
            },
            'appointments': {
                'total': appointments.count(),
                'completed': appointments.filter(status='COMPLETED').count(),
                'cancelled': appointments.filter(status='CANCELLED').count(),
                'no_shows': appointments.filter(is_no_show=True).count(),
                'pending': appointments.filter(status='PENDING').count()
            },
            'revenue': {
                'total': total_revenue,
                'average_per_appointment': total_revenue / completed_services.count() if completed_services.count() > 0 else 0
            },
            'services': {
                'most_popular': services.values(
                    'service__name'
                ).annotate(
                    count=Count('id')
                ).order_by('-count')[:5],
                'total_duration': sum((service.end_time - service.start_time).total_seconds() / 3600 for service in services)
            },
            'staff_performance': staff_metrics,
            'busiest_days': services.annotate(
                date=TruncDate('start_time')
            ).values('date').annotate(
                count=Count('id')
            ).order_by('-count')[:5]
        }
    except Exception as e:
        logger.error(f"Error calculating business metrics: {str(e)}")
        return None

def validate_appointment_services(appointment_services):
    """
    Validate that appointment services don't overlap and are in valid order
    
    Args:
        appointment_services: List of AppointmentService instances
        
    Returns:
        tuple: (bool, str) - (is_valid, error_message)
    """
    if not appointment_services:
        return False, "No services provided"
    
    try:
        # Sort services by start time
        sorted_services = sorted(appointment_services, key=lambda x: x.start_time)
        
        # Check each service
        for i, service in enumerate(sorted_services):
            # Validate service duration
            expected_duration = service.service.duration
            actual_duration = service.end_time - service.start_time
            if actual_duration != expected_duration:
                return False, f"Invalid duration for service: {service.service.name}"
            
            # Check for overlaps with next service
            if i < len(sorted_services) - 1:
                next_service = sorted_services[i + 1]
                if service.end_time > next_service.start_time:
                    return False, "Services overlap"
                
                # Check if there's too big a gap between services
                gap = (next_service.start_time - service.end_time).total_seconds() / 60
                if gap > 30:  # More than 30 minutes gap
                    return False, "Too large gap between services"
            
            # Validate staff availability
            if not is_staff_available(service):
                return False, f"Staff not available for service: {service.service.name}"
        
        return True, "Valid services schedule"
        
    except Exception as e:
        logger.error(f"Error validating appointment services: {str(e)}")
        return False, "Error validating services"

def is_staff_available(appointment_service):
    """
    Check if staff is available for the given appointment service
    
    Args:
        appointment_service: AppointmentService instance
        
    Returns:
        bool: True if staff is available, False otherwise
    """
    try:
        # Check staff schedule
        schedule_exists = Schedule.objects.filter(
            staff=appointment_service.staff,
            date=appointment_service.start_time.date(),
            start_time__lte=appointment_service.start_time.time(),
            end_time__gte=appointment_service.end_time.time()
        ).exists()
        
        if not schedule_exists:
            return False
        
        # Check for conflicting appointments
        conflicts = AppointmentService.objects.filter(
            staff=appointment_service.staff,
            start_time__lt=appointment_service.end_time,
            end_time__gt=appointment_service.start_time,
            appointment__status__in=['PENDING', 'CONFIRMED', 'IN_PROGRESS']
        ).exclude(id=appointment_service.id).exists()
        
        return not conflicts
        
    except Exception as e:
        logger.error(f"Error checking staff availability: {str(e)}")
        return False

def format_time_slot(start_time, end_time):
    """
    Format a time slot into a human-readable string
    
    Args:
        start_time: datetime
        end_time: datetime
        
    Returns:
        str: Formatted time slot string
    """
    try:
        return f"{start_time.strftime('%I:%M %p')} - {end_time.strftime('%I:%M %p')}"
    except Exception as e:
        logger.error(f"Error formatting time slot: {str(e)}")
        return ""