from django.urls import path, include
from rest_framework.routers import DefaultRouter
from drf_yasg.views import get_schema_view
from drf_yasg import openapi
from rest_framework import permissions
from .views import (
    BusinessViewSet, ServiceViewSet, AppointmentViewSet, 
    ScheduleViewSet, StaffViewSet, AuthViewSet, 
    BusinessAnalyticsView
)
from .admin_views import LogViewerView

# Create router
router = DefaultRouter()
router.register(r'businesses', BusinessViewSet, basename='business')
router.register(r'services', ServiceViewSet, basename='service')
router.register(r'appointments', AppointmentViewSet, basename='appointment')
router.register(r'schedules', ScheduleViewSet, basename='schedule')
router.register(r'staff', StaffViewSet, basename='staff')

# Schema view for API documentation
schema_view = get_schema_view(
    openapi.Info(
        title="Clinic Booking API",
        default_version='v1',
        description="API for managing clinic bookings and appointments",
        terms_of_service="https://www.yourapp.com/terms/",
        contact=openapi.Contact(email="contact@yourapp.com"),
        license=openapi.License(name="BSD License"),
    ),
    public=True,
    permission_classes=(permissions.AllowAny,),
)

urlpatterns = [
    # Authentication endpoints
    path('auth/', include([
        path('business/register/', 
             AuthViewSet.as_view({'post': 'business_register'}), 
             name='business-register'),
        path('staff/register/', 
             AuthViewSet.as_view({'post': 'staff_register'}), 
             name='staff-register'),
        path('login/', 
             AuthViewSet.as_view({'post': 'login'}), 
             name='login'),
    ])),
    
    # Analytics endpoints
    path('analytics/', include([
        path('business/', 
             BusinessAnalyticsView.as_view(), 
             name='business-analytics'),
        path('business/<int:business_id>/', 
             BusinessAnalyticsView.as_view(), 
             name='business-analytics-detail'),
    ])),
    
    # Staff management endpoints
    path('staff/', include([
        path('<int:staff_id>/schedule/', 
             StaffViewSet.as_view({'get': 'schedule'}), 
             name='staff-schedule'),
        path('<int:staff_id>/appointments/', 
             StaffViewSet.as_view({'get': 'appointments'}), 
             name='staff-appointments'),
    ])),
    
    # Appointment management endpoints
    path('appointments/', include([
        path('<int:pk>/change-status/', 
             AppointmentViewSet.as_view({'post': 'change_status'}), 
             name='appointment-change-status'),
        path('slots/', 
             AppointmentViewSet.as_view({'get': 'available_slots'}), 
             name='appointment-slots'),
    ])),
    
    # Business management endpoints
    path('business/', include([
        path('<int:business_id>/services/', 
             ServiceViewSet.as_view({'get': 'list', 'post': 'create'}), 
             name='business-services'),
        path('<int:business_id>/staff/', 
             StaffViewSet.as_view({'get': 'list', 'post': 'create'}), 
             name='business-staff'),
        path('<int:business_id>/schedules/', 
             ScheduleViewSet.as_view({'get': 'list', 'post': 'create'}), 
             name='business-schedules'),
    ])),
    
    # Admin views
    path('admin/', include([
        path('logs/', LogViewerView.as_view(), name='admin-logs'),
    ])),
    
    # API Documentation
    path('swagger<format>/', schema_view.without_ui(cache_timeout=0), name='schema-json'),
    path('swagger/', schema_view.with_ui('swagger', cache_timeout=0), name='schema-swagger-ui'),
    path('redoc/', schema_view.with_ui('redoc', cache_timeout=0), name='schema-redoc'),
    
    # Default router URLs
    path('', include(router.urls)),
]