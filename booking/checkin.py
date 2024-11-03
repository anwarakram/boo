# checkin.py
import qrcode
import uuid
from datetime import datetime, timedelta
from django.utils import timezone
from django.conf import settings
from .models import Appointment, AppointmentService
from .logging_system import LoggingService

class CheckInManager:
    @staticmethod
    def generate_qr_code(appointment):
        """Generate unique QR code for appointment"""
        unique_id = str(uuid.uuid4())
        appointment.qr_code = unique_id
        appointment.save()
        
        # QR code data
        qr_data = {
            'appointment_id': appointment.id,
            'qr_code': unique_id,
            'customer_id': appointment.customer.id,
            'appointment_time': appointment.services.first().start_time.isoformat()
        }
        
        # Generate QR code image
        qr = qrcode.QRCode(version=1, box_size=10, border=5)
        qr.add_data(str(qr_data))
        qr.make(fit=True)
        
        return qr.make_image(fill_color="black", back_color="white")

    @staticmethod
    def process_check_in(qr_code):
        """Process customer check-in"""
        try:
            appointment = Appointment.objects.get(qr_code=qr_code)
            first_service = appointment.services.order_by('start_time').first()
            current_time = timezone.now()
            
            # Validate appointment
            if appointment.status in ['CANCELLED', 'COMPLETED', 'NO_SHOW']:
                raise ValueError("Invalid appointment status")
            
            # Calculate time difference
            time_difference = first_service.start_time - current_time
            
            # Handle early arrival
            if time_difference > timedelta(minutes=30):
                appointment.early_arrival = True
                return {
                    'status': 'EARLY',
                    'time_difference': time_difference,
                    'appointment': appointment
                }
            
            # Normal check-in
            appointment.status = 'CHECKED_IN'
            appointment.check_in_time = current_time
            appointment.actual_arrival_time = current_time
            appointment.save()
            
            LoggingService.log_action(
                user=appointment.customer.user,
                action='CHECK_IN',
                content_object=appointment,
                details={'check_in_time': current_time.isoformat()}
            )
            
            return {
                'status': 'SUCCESS',
                'appointment': appointment
            }
            
        except Appointment.DoesNotExist:
            raise ValueError("Invalid QR code")
        except Exception as e:
            LoggingService.log_error(
                error=e,
                severity='ERROR',
                endpoint='check_in'
            )
            raise

    @staticmethod
    def handle_early_arrival(appointment):
        """Handle early arrival cases"""
        first_service = appointment.services.order_by('start_time').first()
        current_time = timezone.now()
        
        # Check for available earlier slots
        available_slot = AppointmentService.objects.filter(
            staff=first_service.staff,
            start_time__gte=current_time,
            start_time__lt=first_service.start_time,
            appointment__status='CANCELLED'
        ).first()
        
        if available_slot:
            return {
                'status': 'SLOT_AVAILABLE',
                'available_time': available_slot.start_time
            }
        
        # Check clinic capacity
        current_appointments = Appointment.objects.filter(
            business=appointment.business,
            status__in=['CHECKED_IN', 'IN_PROGRESS']
        ).count()
        
        if current_appointments < appointment.business.max_concurrent_appointments:
            return {
                'status': 'CAN_WAIT',
                'estimated_wait': first_service.start_time
            }
        
        return {
            'status': 'RETURN_LATER',
            'original_time': first_service.start_time
        }