from rest_framework.schemas import AutoSchema
from rest_framework.schemas.openapi import AutoSchema as OpenAPISchema

class BookingSchema(OpenAPISchema):
    def get_operation_id(self, path, method):
        """
        Provide operation ID for API documentation
        """
        method_name = method.lower()
        if path.endswith('/'):
            path = path[:-1]
        
        path_parts = path.split('/')
        operation_id = []
        
        if 'auth' in path_parts:
            operation_id.append('auth')
        elif 'business' in path_parts:
            operation_id.append('business')
        elif 'staff' in path_parts:
            operation_id.append('staff')
        elif 'appointments' in path_parts:
            operation_id.append('appointment')
        elif 'services' in path_parts:
            operation_id.append('service')
        elif 'schedules' in path_parts:
            operation_id.append('schedule')
        
        if method_name == 'get':
            if '{id}' in path or '{pk}' in path:
                operation_id.append('retrieve')
            else:
                operation_id.append('list')
        elif method_name == 'post':
            operation_id.append('create')
        elif method_name == 'put':
            operation_id.append('update')
        elif method_name == 'patch':
            operation_id.append('partial_update')
        elif method_name == 'delete':
            operation_id.append('delete')
            
        return '_'.join(operation_id)

    def get_components(self, path, method):
        """
        Define components for API documentation
        """
        components = super().get_components(path, method)
        
        # Add common error responses
        components['responses'] = {
            '400': {
                'description': 'Bad Request - Invalid input data',
                'content': {
                    'application/json': {
                        'schema': {
                            'type': 'object',
                            'properties': {
                                'error': {
                                    'type': 'string'
                                }
                            }
                        }
                    }
                }
            },
            '401': {
                'description': 'Unauthorized - Authentication required',
            },
            '403': {
                'description': 'Forbidden - Insufficient permissions',
            },
            '404': {
                'description': 'Not Found - Requested resource does not exist',
            },
            '500': {
                'description': 'Internal Server Error',
            }
        }
        
        return components