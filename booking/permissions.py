from rest_framework import permissions

class IsSystemAdmin(permissions.BasePermission):
    """
    Permission check for system administrators only.
    """
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.user_type == 'SYSTEM_ADMIN'

class IsBusinessAdminOrSystemAdmin(permissions.BasePermission):
    """
    Permission check for business admins and system admins.
    """
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        return request.user.user_type in ['BUSINESS_ADMIN', 'SYSTEM_ADMIN']

    def has_object_permission(self, request, view, obj):
        if request.user.user_type == 'SYSTEM_ADMIN':
            return True
            
        if hasattr(obj, 'business'):
            return obj.business == request.user.business
        if hasattr(obj, 'user'):
            return obj.user.business == request.user.business
        return False

class IsStaffOrBusinessAdminOrSystemAdmin(permissions.BasePermission):
    """
    Permission check for staff members, business admins, and system admins.
    """
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        return request.user.user_type in ['STAFF', 'BUSINESS_ADMIN', 'SYSTEM_ADMIN']

    def has_object_permission(self, request, view, obj):
        if request.user.user_type == 'SYSTEM_ADMIN':
            return True
            
        if request.user.user_type in ['BUSINESS_ADMIN', 'STAFF']:
            if hasattr(obj, 'business'):
                return obj.business == request.user.business
            if hasattr(obj, 'user'):
                return obj.user.business == request.user.business
        return False

class IsBusinessAdmin(permissions.BasePermission):
    """
    Permission check for business admins only.
    """
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.user_type == 'BUSINESS_ADMIN'

    def has_object_permission(self, request, view, obj):
        if hasattr(obj, 'business'):
            return obj.business == request.user.business
        if hasattr(obj, 'user'):
            return obj.user.business == request.user.business
        return False

class IsStaff(permissions.BasePermission):
    """
    Permission check for staff members only.
    """
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.user_type == 'STAFF'

    def has_object_permission(self, request, view, obj):
        if hasattr(obj, 'business'):
            return obj.business == request.user.business
        if hasattr(obj, 'user'):
            return obj.user.business == request.user.business
        return False

class HasBusinessAccess(permissions.BasePermission):
    """
    Permission check for users with access to a specific business.
    """
    def has_object_permission(self, request, view, obj):
        if not request.user.is_authenticated:
            return False
            
        if request.user.user_type == 'SYSTEM_ADMIN':
            return True
            
        if hasattr(obj, 'business'):
            return obj.business == request.user.business
        if hasattr(obj, 'user'):
            return obj.user.business == request.user.business
        return False

class CanManageStaff(permissions.BasePermission):
    """
    Permission check for users who can manage staff (Business Admin and System Admin).
    """
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        return request.user.user_type in ['BUSINESS_ADMIN', 'SYSTEM_ADMIN']

    def has_object_permission(self, request, view, obj):
        if request.user.user_type == 'SYSTEM_ADMIN':
            return True
            
        if request.user.user_type == 'BUSINESS_ADMIN':
            return obj.business == request.user.business
        return False

class CanManageAppointments(permissions.BasePermission):
    """
    Permission check for users who can manage appointments (Staff and Business Admin).
    """
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        return request.user.user_type in ['STAFF', 'BUSINESS_ADMIN']

    def has_object_permission(self, request, view, obj):
        if hasattr(obj, 'business'):
            return obj.business == request.user.business
        return False

class CanViewAnalytics(permissions.BasePermission):
    """
    Permission check for users who can view analytics (Business Admin and System Admin).
    """
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        return request.user.user_type in ['BUSINESS_ADMIN', 'SYSTEM_ADMIN']

    def has_object_permission(self, request, view, obj):
        if request.user.user_type == 'SYSTEM_ADMIN':
            return True
            
        if request.user.user_type == 'BUSINESS_ADMIN':
            return obj.business == request.user.business
        return False