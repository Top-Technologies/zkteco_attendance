{
    'name': 'ZKTeco Attendance Machine',
    'version': '18.0.1.0.0',
    'category': 'Human Resources',
    'summary': 'Odoo Integration with ZKTeco for real-time attendance tracking',
    'description': """
        Odoo 18 integration with ZKTeco Fingerprint Machine.
        
        Features:
        - Real-time attendance synchronization via Flask ADMS middleware
        - Device management and monitoring
        - User mapping between ZKTeco devices and Odoo employees
        - Quarantine management for invalid records
        - Automatic attendance processing
        - Daily attendance records with status tracking (Present/Absent/Missed Punch)
        - Automatic absence marking for employees who fail to punch in
        - Shift management
        - Comprehensive reporting
    """,
    'author': 'Top Tech',
    'website': 'https://www.odoo.com',
    'depends': ['base', 'hr', 'hr_attendance', 'hr_holidays', 'mail'],
    'external_dependencies': {
        'python': ['requests'],
    },
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'views/device_views.xml',
        'views/branch_views.xml',
        'data/cron.xml',
        'data/dashboard_data.xml',

        'views/attendance_views.xml',
        'views/mapping_views.xml',
        'views/hr_employee_views.xml',
        'views/shift_views.xml',
        'views/work_policy_views.xml',
        'views/attendance_report_views.xml',
        'views/quarantine_views.xml',
        'views/adms_config_views.xml',
        'views/attendance_record_views.xml',
        'views/zkteco_reports_views.xml',
        'views/monthly_attendance_views.xml',
        'views/historical_sync_views.xml',
        'views/detailed_attendance_report_views.xml',
        'views/attendance_dashboard_views.xml',
        'views/cloud_config_views.xml',
        'views/kpi_dashboard_views.xml',
        'wizard/manual_present_wizard_views.xml',
        'wizard/auto_rotate_wizard_views.xml',
    ],

    'assets': {
        'web.assets_backend': [
            'https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js',
            'zkteco_attendance/static/src/css/dashboard.css',
            'zkteco_attendance/static/src/css/kpi_dashboard.css',
            'zkteco_attendance/static/src/xml/kpi_dashboard.xml',
            'zkteco_attendance/static/src/js/kpi_dashboard.js',
        ],
    },

    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}

