from django.contrib import admin
from django.utils import timezone
from django.db.models import Count, Avg
from datetime import timedelta
from django.urls import path
from django.template.response import TemplateResponse
from .models import (
    CustomUser, Business, Service, 
    Appointment, Schedule, DailyAnalytics,
    AppointmentService
)
from .logging_system import AuditLog, ErrorLog

class CustomUserAdmin(admin.ModelAdmin):
    model = CustomUser
    list_display = ('email', 'user_type', 'is_staff', 'is_active', 'business', 'date_joined')
    list_filter = ('user_type', 'is_staff', 'is_active', 'business')
    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Personal info', {'fields': ('first_name', 'last_name')}),
        ('Permissions', {'fields': ('user_type', 'is_staff', 'is_active', 'groups', 'user_permissions')}),
        ('Business', {'fields': ('business',)}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'password1', 'password2', 'user_type', 'is_staff', 'is_active', 'business', 'first_name', 'last_name')}
        ),
    )
    search_fields = ('email', 'first_name', 'last_name')
    ordering = ('email',)
    filter_horizontal = ('groups', 'user_permissions',)

class BusinessAdmin(admin.ModelAdmin):
    list_display = ('name', 'phone', 'address', 'created_at', 'get_staff_count', 'get_active_services')
    list_filter = ('created_at',)
    search_fields = ('name', 'phone', 'address')
    readonly_fields = ('created_at',)
    
    def get_staff_count(self, obj):
        return CustomUser.objects.filter(business=obj, user_type='STAFF').count()
    get_staff_count.short_description = 'Staff Count'
    
    def get_active_services(self, obj):
        return Service.objects.filter(business=obj).count()
    get_active_services.short_description = 'Active Services'

class ServiceAdmin(admin.ModelAdmin):
    list_display = ('name', 'business', 'duration', 'price', 'get_appointment_count')
    list_filter = ('business', 'duration')
    search_fields = ('name', 'business__name')
    ordering = ('business', 'name')
    
    def get_appointment_count(self, obj):
        return AppointmentService.objects.filter(service=obj).count()
    get_appointment_count.short_description = 'Total Appointments'

class AppointmentServiceInline(admin.TabularInline):
    model = AppointmentService
    extra = 1
    fields = ('service', 'staff', 'start_time', 'end_time', 'price')

class AppointmentAdmin(admin.ModelAdmin):
    inlines = [AppointmentServiceInline]
    list_display = (
        'id', 'business', 'client_name', 'client_phone', 'status',
        'total_price', 'created_at', 'updated_at'
    )
    list_filter = ('business', 'status', 'created_at')
    search_fields = (
        'client_name', 'client_phone',
        'services__staff__email', 'services__staff__first_name', 
        'services__staff__last_name'
    )
    readonly_fields = ('created_at', 'updated_at', 'total_price')
    fieldsets = (
        ('Client Information', {
            'fields': ('business', 'client_name', 'client_phone', 'status', 'total_price')
        }),
        ('Additional Information', {
            'fields': ('notes', 'created_at', 'updated_at')
        }),
    )

class ScheduleAdmin(admin.ModelAdmin):
    list_display = ('business', 'staff', 'date', 'start_time', 'end_time', 'get_appointment_count')
    list_filter = ('business', 'date', 'staff')
    search_fields = ('staff__email', 'staff__first_name', 'staff__last_name')
    ordering = ('-date', 'start_time')
    date_hierarchy = 'date'
    
    def get_appointment_count(self, obj):
        return AppointmentService.objects.filter(
            staff=obj.staff,
            start_time__date=obj.date
        ).count()
    get_appointment_count.short_description = 'Appointments'

class DailyAnalyticsAdmin(admin.ModelAdmin):
    list_display = (
        'business', 'date', 'total_appointments',
        'cancellations', 'total_revenue'
    )
    list_filter = ('business', 'date')
    search_fields = ('business__name',)
    date_hierarchy = 'date'
    readonly_fields = ('total_revenue', 'avg_service_duration')

class AuditLogAdmin(admin.ModelAdmin):
    list_display = ('timestamp', 'user', 'action', 'ip_address', 'endpoint')
    list_filter = ('action', 'timestamp')
    search_fields = ('user__email', 'action', 'details')
    readonly_fields = ('timestamp', 'user', 'action', 'ip_address', 'user_agent', 'endpoint', 'details')
    date_hierarchy = 'timestamp'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser

class ErrorLogAdmin(admin.ModelAdmin):
    list_display = ('timestamp', 'severity', 'error_type', 'error_message', 'user')
    list_filter = ('severity', 'error_type', 'timestamp')
    search_fields = ('error_message', 'error_type', 'user__email')
    readonly_fields = ('timestamp', 'severity', 'error_type', 'error_message', 'traceback', 'user', 'endpoint', 'request_data')
    date_hierarchy = 'timestamp'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser

# Register all models
admin.site.register(CustomUser, CustomUserAdmin)
admin.site.register(Business, BusinessAdmin)
admin.site.register(Service, ServiceAdmin)
admin.site.register(Appointment, AppointmentAdmin)
admin.site.register(AppointmentService)
admin.site.register(Schedule, ScheduleAdmin)
admin.site.register(DailyAnalytics, DailyAnalyticsAdmin)
admin.site.register(AuditLog, AuditLogAdmin)
admin.site.register(ErrorLog, ErrorLogAdmin)

# Customize admin site
admin.site.site_header = 'Clinic Booking Administration'
admin.site.site_title = 'Clinic Booking Admin Portal'
admin.site.index_title = 'Welcome to Clinic Booking Admin Portal'