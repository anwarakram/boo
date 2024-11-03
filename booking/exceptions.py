from rest_framework.exceptions import APIException
from rest_framework import status
from django.utils.translation import gettext_lazy as _

class BookingBaseException(APIException):
    """Base exception for booking app"""
    pass

class AppointmentError(BookingBaseException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = _('An error occurred with the appointment.')
    default_code = 'appointment_error'

class InvalidTimeSlotError(AppointmentError):
    default_detail = _('The selected time slot is invalid.')
    default_code = 'invalid_time_slot'

class DoubleBookingError(AppointmentError):
    default_detail = _('This time slot is already booked.')
    default_code = 'double_booking'

class OutsideBusinessHoursError(AppointmentError):
    default_detail = _('Appointment time is outside business hours.')
    default_code = 'outside_hours'

class StaffUnavailableError(AppointmentError):
    default_detail = _('Selected staff is not available at this time.')
    default_code = 'staff_unavailable'

class PastDateError(AppointmentError):
    default_detail = _('Cannot book appointments in the past.')
    default_code = 'past_date'

class CancellationError(AppointmentError):
    default_detail = _('Cannot cancel appointment at this time.')
    default_code = 'cancellation_error'

class ValidationError(BookingBaseException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = _('Invalid data provided.')
    default_code = 'validation_error'

class BusinessError(BookingBaseException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = _('Business operation error.')
    default_code = 'business_error'

class ResourceNotFoundError(BookingBaseException):
    status_code = status.HTTP_404_NOT_FOUND
    default_detail = _('Requested resource not found.')
    default_code = 'not_found'

class AuthenticationError(BookingBaseException):
    status_code = status.HTTP_401_UNAUTHORIZED
    default_detail = _('Authentication failed.')
    default_code = 'authentication_error'

class PermissionError(BookingBaseException):
    status_code = status.HTTP_403_FORBIDDEN
    default_detail = _('Permission denied.')
    default_code = 'permission_denied'