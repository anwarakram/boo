from django.db import models
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.core.validators import MinValueValidator, MaxValueValidator
from datetime import timedelta

class CustomUserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('The Email field must be set')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('user_type', 'SYSTEM_ADMIN')

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')
        if extra_fields.get('user_type') != 'SYSTEM_ADMIN':
            raise ValueError('Superuser must have user_type=SYSTEM_ADMIN.')

        return self.create_user(email, password, **extra_fields)

class CustomUser(AbstractUser):
    USER_TYPE_CHOICES = (
        ('SYSTEM_ADMIN', 'System Admin'),
        ('BUSINESS_ADMIN', 'Business Admin'),
        ('STAFF', 'Staff'),
    )

    username = None  # Remove username field
    email = models.EmailField('email address', unique=True)
    user_type = models.CharField(max_length=20, choices=USER_TYPE_CHOICES)
    business = models.ForeignKey('Business', on_delete=models.CASCADE, null=True, blank=True)
    last_login_ip = models.GenericIPAddressField(null=True, blank=True)
    last_login_device = models.CharField(max_length=255, null=True, blank=True)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['user_type']

    objects = CustomUserManager()

    def __str__(self):
        return self.email

class Business(models.Model):
    name = models.CharField(max_length=100)
    address = models.TextField()
    phone = models.CharField(max_length=20)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name_plural = "Businesses"

class Service(models.Model):
    PRICE_TYPE_CHOICES = (
        ('FIXED', 'Fixed price'),
        ('VARIABLE', 'Variable price'),
    )
    
    COLOR_CHOICES = (
        ('BLUE', 'Blue'),
        ('GREEN', 'Green'),
        ('PURPLE', 'Purple'),
        ('RED', 'Red'),
    )

    business = models.ForeignKey(Business, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    duration = models.DurationField()
    price_type = models.CharField(max_length=10, choices=PRICE_TYPE_CHOICES, default='FIXED')
    price = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    color = models.CharField(max_length=10, choices=COLOR_CHOICES, default='BLUE')
    description = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        unique_together = ('business', 'name')

    def __str__(self):
        return f"{self.name} - {self.business.name}"

class Appointment(models.Model):
    APPOINTMENT_STATUS = [
        ('PENDING', 'Pending'),
        ('CONFIRMED', 'Confirmed'),
        ('IN_PROGRESS', 'In Progress'),
        ('COMPLETED', 'Completed'),
        ('CANCELLED', 'Cancelled'),
    ]

    business = models.ForeignKey(Business, on_delete=models.CASCADE)
    client_name = models.CharField(max_length=100, default='Anonymous')
    client_phone = models.CharField(max_length=20, default='') 
    status = models.CharField(max_length=20, choices=APPOINTMENT_STATUS, default='PENDING')
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    total_price = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        validators=[MinValueValidator(0)], 
        default=0
    )

    def calculate_total_price(self):
        return sum(service.price for service in self.services.all())

    def save(self, *args, **kwargs):
        self.total_price = self.calculate_total_price()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.client_name} - {self.created_at.date()}"

class AppointmentService(models.Model):
    appointment = models.ForeignKey(Appointment, on_delete=models.CASCADE, related_name='services')
    service = models.ForeignKey(Service, on_delete=models.CASCADE)
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    staff = models.ForeignKey(
        CustomUser, 
        on_delete=models.SET_NULL, 
        null=True, 
        limit_choices_to={'user_type': 'STAFF'}
    )
    price = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])

    class Meta:
        ordering = ['start_time']

    def clean(self):
        if self.start_time >= self.end_time:
            raise ValidationError("End time must be after start time")
        if self.start_time < timezone.now():
            raise ValidationError("Cannot book appointments in the past")
        
        # Check staff availability
        staff_appointments = AppointmentService.objects.filter(
            staff=self.staff,
            start_time__lt=self.end_time,
            end_time__gt=self.start_time
        ).exclude(pk=self.pk)
        
        if staff_appointments.exists():
            raise ValidationError("The selected staff member is not available during this time slot")

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.service.name} - {self.start_time}"

class Schedule(models.Model):
    business = models.ForeignKey(Business, on_delete=models.CASCADE)
    staff = models.ForeignKey(
        CustomUser, 
        on_delete=models.CASCADE, 
        limit_choices_to={'user_type': 'STAFF'}
    )
    date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()

    def clean(self):
        if self.start_time >= self.end_time:
            raise ValidationError("End time must be after start time")
        
        overlapping_schedules = Schedule.objects.filter(
            staff=self.staff,
            date=self.date,
            start_time__lt=self.end_time,
            end_time__gt=self.start_time
        ).exclude(pk=self.pk)
        
        if overlapping_schedules.exists():
            raise ValidationError("This schedule overlaps with another schedule for this staff member")

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.staff} - {self.date} {self.start_time}-{self.end_time}"

    class Meta:
        unique_together = ('staff', 'date', 'start_time', 'end_time')

class DailyAnalytics(models.Model):
    business = models.ForeignKey(Business, on_delete=models.CASCADE)
    date = models.DateField()
    total_appointments = models.IntegerField(default=0)
    cancellations = models.IntegerField(default=0)
    total_revenue = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    avg_service_duration = models.DurationField(null=True, blank=True)

    class Meta:
        unique_together = ('business', 'date')
        verbose_name_plural = "Daily Analytics"

    def __str__(self):
        return f"Analytics for {self.business} on {self.date}"