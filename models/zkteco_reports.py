"""
ZKTeco Attendance Reports & Audit Models
"""

import logging
from odoo import models, fields, api, tools, _

_logger = logging.getLogger(__name__)


class DailyAttendanceRegister(models.Model):
    """Daily Attendance Register Report."""
    _name = 'zkteco.daily.attendance.register'
    _description = 'Daily Attendance Register'
    _auto = False
    _order = 'date desc, employee_id'

    employee_id = fields.Many2one('hr.employee', string='Employee', readonly=True)
    department_id = fields.Many2one('hr.department', string='Department', readonly=True)
    employee_branch_id = fields.Many2one('zkteco.branch', string='Branch', readonly=True)
    date = fields.Date(string='Date', readonly=True)
    shift_id = fields.Many2one('zkteco.shift', string='Shift', readonly=True)

    first_checkin = fields.Datetime(string='First Check-in', readonly=True)
    last_checkout = fields.Datetime(string='Last Check-out', readonly=True)
    total_punches = fields.Integer(string='Total Punches', readonly=True)

    worked_hours = fields.Float(string='Worked Hours', readonly=True)
    expected_hours = fields.Float(string='Expected Hours', readonly=True)
    late_minutes = fields.Integer(string='Late Minutes', readonly=True)
    early_leave_minutes = fields.Integer(string='Early Leave Minutes', readonly=True)
    overtime_hours = fields.Float(string='Overtime Hours', readonly=True)

    status = fields.Selection([
        ('present', 'Present'),
        ('absent', 'Absent'),
        ('missed_punch', 'Missed Punch'),
        ('on_leave', 'On Leave'),
    ], string='Status', readonly=True)

    is_late = fields.Boolean(string='Is Late', readonly=True)
    is_early_leave = fields.Boolean(string='Is Early Leave', readonly=True)
    leave_id = fields.Many2one('hr.leave', string='Time Off Request', readonly=True)
    leave_type_id = fields.Many2one('hr.leave.type', string='Time Off Type', readonly=True)
    is_half_day_leave = fields.Boolean(string='Half Day Leave', readonly=True)
    is_paid_leave = fields.Boolean(string='Is Paid Leave', readonly=True)
    leave_state = fields.Selection([
        ('draft', 'Draft'),
        ('confirm', 'Requested'),
        ('validate1', 'Second Approval'),
        ('validate', 'Approved'),
    ], string='Leave Approval State', readonly=True)
    remarks = fields.Text(string='Remarks', readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %s AS (
                SELECT
                    ar.id as id,
                    ar.employee_id as employee_id,
                    ar.department_id as department_id,
                    ar.employee_branch_id as employee_branch_id,
                    ar.date as date,
                    ar.shift_id as shift_id,
                    ar.first_checkin as first_checkin,
                    ar.last_checkout as last_checkout,
                    ar.total_punches as total_punches,
                    ar.worked_hours as worked_hours,
                    ar.expected_hours as expected_hours,
                    COALESCE(ar.late_minutes, 0) as late_minutes,
                    COALESCE(ar.early_leave_minutes, 0) as early_leave_minutes,
                    COALESCE(ar.overtime_hours, 0) as overtime_hours,
                    ar.status as status,
                    ar.is_late as is_late,
                    ar.is_early_leave as is_early_leave,
                    ar.leave_id as leave_id,
                    ar.leave_type_id as leave_type_id,
                    ar.is_half_day_leave as is_half_day_leave,
                    ar.is_paid_leave as is_paid_leave,
                    ar.leave_state as leave_state,
                    ar.remarks as remarks
                FROM zkteco_attendance_record ar
                WHERE ar.employee_id IS NOT NULL
            )
        """ % self._table)


class MonthlyAttendanceSummary(models.Model):
    """Monthly Attendance Summary Report."""
    _name = 'zkteco.monthly.attendance.summary'
    _description = 'Monthly Attendance Summary'
    _auto = False
    _order = 'year_month desc, employee_id'

    employee_id = fields.Many2one('hr.employee', string='Employee', readonly=True)
    department_id = fields.Many2one('hr.department', string='Department', readonly=True)
    employee_branch_id = fields.Many2one('zkteco.branch', string='Branch', readonly=True)
    year_month = fields.Char(string='Year-Month', readonly=True)
    month_start = fields.Date(string='Month Start', readonly=True)

    total_days = fields.Integer(string='Total Days Record', readonly=True)
    present_days = fields.Integer(string='Present Days', readonly=True)
    absent_days = fields.Integer(string='Absent Days', readonly=True)
    on_leave_days = fields.Integer(string='Leave Days', readonly=True)
    paid_leave_days = fields.Float(string='Paid Leave Days', readonly=True)
    unpaid_leave_days = fields.Float(string='Unpaid Leave Days', readonly=True)
    half_day_leave_days = fields.Float(string='Half Day Leave Count', readonly=True)
    missed_punch_days = fields.Integer(string='Missed Punch Days', readonly=True)
    late_days = fields.Integer(string='Late Days', readonly=True)
    early_leave_days = fields.Integer(string='Early Departure Days', readonly=True)

    total_worked_hours = fields.Float(string='Total Worked Hours', readonly=True)
    total_expected_hours = fields.Float(string='Total Expected Hours', readonly=True)
    total_overtime_hours = fields.Float(string='Total Overtime Hours', readonly=True)
    total_late_minutes = fields.Integer(string='Total Late Minutes', readonly=True)
    total_early_minutes = fields.Integer(string='Total Early Minutes', readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %s AS (
                SELECT
                    (ar.employee_id::text || '_' || TO_CHAR(ar.date, 'YYYYMM'))::text as id,
                    ar.employee_id as employee_id,
                    ar.department_id as department_id,
                    ar.employee_branch_id as employee_branch_id,
                    TO_CHAR(ar.date, 'YYYY-MM') as year_month,
                    DATE_TRUNC('month', ar.date)::date as month_start,
                    COUNT(ar.id) as total_days,
                    SUM(CASE WHEN ar.status = 'present' THEN 1 ELSE 0 END) as present_days,
                    SUM(CASE WHEN ar.status = 'absent' THEN 1 ELSE 0 END) as absent_days,
                    SUM(CASE WHEN ar.status = 'on_leave' THEN 1 ELSE 0 END) as on_leave_days,
                    SUM(CASE WHEN ar.status = 'on_leave' AND ar.is_paid_leave = TRUE THEN (CASE WHEN ar.is_half_day_leave = TRUE THEN 0.5 ELSE 1.0 END) ELSE 0 END) as paid_leave_days,
                    SUM(CASE WHEN ar.status = 'on_leave' AND ar.is_paid_leave = FALSE THEN (CASE WHEN ar.is_half_day_leave = TRUE THEN 0.5 ELSE 1.0 END) ELSE 0 END) as unpaid_leave_days,
                    SUM(CASE WHEN ar.is_half_day_leave = TRUE THEN 1 ELSE 0 END) as half_day_leave_days,
                    SUM(CASE WHEN ar.status = 'missed_punch' THEN 1 ELSE 0 END) as missed_punch_days,
                    SUM(CASE WHEN ar.is_late = TRUE THEN 1 ELSE 0 END) as late_days,
                    SUM(CASE WHEN ar.is_early_leave = TRUE THEN 1 ELSE 0 END) as early_leave_days,
                    COALESCE(SUM(ar.worked_hours), 0) as total_worked_hours,
                    COALESCE(SUM(ar.expected_hours), 0) as total_expected_hours,
                    COALESCE(SUM(ar.overtime_hours), 0) as total_overtime_hours,
                    COALESCE(SUM(ar.late_minutes), 0) as total_late_minutes,
                    COALESCE(SUM(ar.early_leave_minutes), 0) as total_early_minutes
                FROM zkteco_attendance_record ar
                WHERE ar.employee_id IS NOT NULL
                GROUP BY ar.employee_id, ar.department_id, ar.employee_branch_id, TO_CHAR(ar.date, 'YYYYMM'), TO_CHAR(ar.date, 'YYYY-MM'), DATE_TRUNC('month', ar.date)

            )
        """ % self._table)



class EmployeeTimesheetReport(models.Model):
    """Employee Timesheet Report."""
    _name = 'zkteco.employee.timesheet.report'
    _description = 'Employee Timesheet Report'
    _auto = False
    _order = 'date desc, employee_id'

    employee_id = fields.Many2one('hr.employee', string='Employee', readonly=True)
    department_id = fields.Many2one('hr.department', string='Department', readonly=True)
    employee_branch_id = fields.Many2one('zkteco.branch', string='Branch', readonly=True)
    date = fields.Date(string='Date', readonly=True)
    shift_id = fields.Many2one('zkteco.shift', string='Shift', readonly=True)

    first_checkin = fields.Datetime(string='Check-In', readonly=True)
    last_checkout = fields.Datetime(string='Check-Out', readonly=True)
    total_punches = fields.Integer(string='Punches Count', readonly=True)

    worked_hours = fields.Float(string='Worked Hours', readonly=True)
    expected_hours = fields.Float(string='Expected Hours', readonly=True)
    overtime_hours = fields.Float(string='Overtime Hours', readonly=True)
    late_minutes = fields.Integer(string='Late (mins)', readonly=True)
    early_leave_minutes = fields.Integer(string='Early Leave (mins)', readonly=True)

    status = fields.Selection([
        ('present', 'Present'),
        ('absent', 'Absent'),
        ('missed_punch', 'Missed Punch'),
        ('on_leave', 'On Leave'),
    ], string='Status', readonly=True)
    remarks = fields.Text(string='Remarks', readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %s AS (
                SELECT
                    ar.id as id,
                    ar.employee_id as employee_id,
                    ar.department_id as department_id,
                    ar.employee_branch_id as employee_branch_id,
                    ar.date as date,
                    ar.shift_id as shift_id,
                    ar.first_checkin as first_checkin,
                    ar.last_checkout as last_checkout,
                    ar.total_punches as total_punches,
                    ar.worked_hours as worked_hours,
                    ar.expected_hours as expected_hours,
                    COALESCE(ar.overtime_hours, 0) as overtime_hours,
                    COALESCE(ar.late_minutes, 0) as late_minutes,
                    COALESCE(ar.early_leave_minutes, 0) as early_leave_minutes,
                    ar.status as status,
                    ar.remarks as remarks
                FROM zkteco_attendance_record ar
                WHERE ar.employee_id IS NOT NULL
            )
        """ % self._table)


class OvertimeReport(models.Model):
    """Overtime Report."""
    _name = 'zkteco.overtime.report'
    _description = 'Overtime Report'
    _auto = False
    _order = 'date desc, overtime_hours desc'

    employee_id = fields.Many2one('hr.employee', string='Employee', readonly=True)
    department_id = fields.Many2one('hr.department', string='Department', readonly=True)
    employee_branch_id = fields.Many2one('zkteco.branch', string='Branch', readonly=True)
    date = fields.Date(string='Date', readonly=True)
    shift_id = fields.Many2one('zkteco.shift', string='Shift', readonly=True)

    first_checkin = fields.Datetime(string='Check-In', readonly=True)
    last_checkout = fields.Datetime(string='Check-Out', readonly=True)
    worked_hours = fields.Float(string='Worked Hours', readonly=True)
    expected_hours = fields.Float(string='Expected Hours', readonly=True)
    overtime_hours = fields.Float(string='Overtime Hours', readonly=True)
    remarks = fields.Text(string='Remarks', readonly=True)

    def action_view_attendance_record(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Daily Attendance Record - %s') % (self.employee_id.name or ''),
            'res_model': 'zkteco.attendance.record',
            'res_id': self.id,
            'view_mode': 'form',
            'views': [(False, 'form')],
            'target': 'current',
        }

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %s AS (
                SELECT
                    ar.id as id,
                    ar.employee_id as employee_id,
                    ar.department_id as department_id,
                    ar.employee_branch_id as employee_branch_id,
                    ar.date as date,
                    ar.shift_id as shift_id,
                    ar.first_checkin as first_checkin,
                    ar.last_checkout as last_checkout,
                    ar.worked_hours as worked_hours,
                    ar.expected_hours as expected_hours,
                    ar.overtime_hours as overtime_hours,
                    ar.remarks as remarks
                FROM zkteco_attendance_record ar
                WHERE ar.employee_id IS NOT NULL AND ar.overtime_hours > 0
            )
        """ % self._table)


class LateEarlyReport(models.Model):
    """Late Arrival & Early Departure Report."""
    _name = 'zkteco.late.early.report'
    _description = 'Late Arrival & Early Departure Report'
    _auto = False
    _order = 'date desc, late_minutes desc, early_leave_minutes desc'

    employee_id = fields.Many2one('hr.employee', string='Employee', readonly=True)
    department_id = fields.Many2one('hr.department', string='Department', readonly=True)
    employee_branch_id = fields.Many2one('zkteco.branch', string='Branch', readonly=True)
    date = fields.Date(string='Date', readonly=True)
    shift_id = fields.Many2one('zkteco.shift', string='Shift', readonly=True)

    first_checkin = fields.Datetime(string='First Check-in', readonly=True)
    last_checkout = fields.Datetime(string='Last Check-out', readonly=True)

    late_minutes = fields.Integer(string='Late Minutes', readonly=True)
    early_leave_minutes = fields.Integer(string='Early Departure Minutes', readonly=True)
    is_late = fields.Boolean(string='Late Arrival', readonly=True)
    is_early_leave = fields.Boolean(string='Early Departure', readonly=True)
    remarks = fields.Text(string='Remarks', readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %s AS (
                SELECT
                    ar.id as id,
                    ar.employee_id as employee_id,
                    ar.department_id as department_id,
                    ar.employee_branch_id as employee_branch_id,
                    ar.date as date,
                    ar.shift_id as shift_id,
                    ar.first_checkin as first_checkin,
                    ar.last_checkout as last_checkout,
                    COALESCE(ar.late_minutes, 0) as late_minutes,
                    COALESCE(ar.early_leave_minutes, 0) as early_leave_minutes,
                    ar.is_late as is_late,
                    ar.is_early_leave as is_early_leave,
                    ar.remarks as remarks
                FROM zkteco_attendance_record ar
                WHERE ar.employee_id IS NOT NULL AND (ar.is_late = TRUE OR ar.is_early_leave = TRUE OR ar.late_minutes > 0 OR ar.early_leave_minutes > 0)
            )
        """ % self._table)


class MissingPunchReport(models.Model):
    """Missing Punch Report."""
    _name = 'zkteco.missing.punch.report'
    _description = 'Missing Punch Report'
    _auto = False
    _order = 'date desc, employee_id'

    employee_id = fields.Many2one('hr.employee', string='Employee', readonly=True)
    department_id = fields.Many2one('hr.department', string='Department', readonly=True)
    employee_branch_id = fields.Many2one('zkteco.branch', string='Branch', readonly=True)
    date = fields.Date(string='Date', readonly=True)
    shift_id = fields.Many2one('zkteco.shift', string='Shift', readonly=True)

    first_checkin = fields.Datetime(string='First Check-in', readonly=True)
    last_checkout = fields.Datetime(string='Last Check-out', readonly=True)
    total_punches = fields.Integer(string='Total Punches', readonly=True)

    missing_type = fields.Selection([
        ('no_checkout', 'Missing Check-Out'),
        ('no_checkin', 'Missing Check-In'),
        ('incomplete', 'Incomplete Punches'),
    ], string='Missing Type', readonly=True)
    remarks = fields.Text(string='Remarks', readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %s AS (
                SELECT
                    ar.id as id,
                    ar.employee_id as employee_id,
                    ar.department_id as department_id,
                    ar.employee_branch_id as employee_branch_id,
                    ar.date as date,
                    ar.shift_id as shift_id,
                    ar.first_checkin as first_checkin,
                    ar.last_checkout as last_checkout,
                    ar.total_punches as total_punches,
                    CASE
                        WHEN ar.first_checkin IS NOT NULL AND ar.last_checkout IS NULL THEN 'no_checkout'
                        WHEN ar.first_checkin IS NULL AND ar.last_checkout IS NOT NULL THEN 'no_checkin'
                        ELSE 'incomplete'
                    END as missing_type,
                    ar.remarks as remarks
                FROM zkteco_attendance_record ar
                WHERE ar.employee_id IS NOT NULL AND (
                    ar.status = 'missed_punch' OR
                    (ar.first_checkin IS NOT NULL AND ar.last_checkout IS NULL) OR
                    (ar.first_checkin IS NULL AND ar.last_checkout IS NOT NULL)
                )
            )
        """ % self._table)


class ShiftComplianceReport(models.Model):
    """Shift Compliance Report."""
    _name = 'zkteco.shift.compliance.report'
    _description = 'Shift Compliance Report'
    _auto = False
    _order = 'employee_id'

    employee_id = fields.Many2one('hr.employee', string='Employee', readonly=True)
    department_id = fields.Many2one('hr.department', string='Department', readonly=True)
    employee_branch_id = fields.Many2one('zkteco.branch', string='Branch', readonly=True)
    shift_id = fields.Many2one('zkteco.shift', string='Shift', readonly=True)

    total_assigned_days = fields.Integer(string='Assigned Days', readonly=True)
    compliant_days = fields.Integer(string='Compliant Days', readonly=True)
    late_count = fields.Integer(string='Late Count', readonly=True)
    early_leave_count = fields.Integer(string='Early Leave Count', readonly=True)
    absent_count = fields.Integer(string='Absent Count', readonly=True)

    total_worked_hours = fields.Float(string='Worked Hours', readonly=True)
    total_expected_hours = fields.Float(string='Expected Hours', readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %s AS (
                SELECT
                    (ar.employee_id::text || '_' || COALESCE(ar.shift_id, 0)::text)::text as id,
                    ar.employee_id as employee_id,
                    ar.department_id as department_id,
                    ar.employee_branch_id as employee_branch_id,
                    ar.shift_id as shift_id,
                    COUNT(ar.id) as total_assigned_days,
                    SUM(CASE WHEN ar.status = 'present' AND ar.is_late = FALSE AND ar.is_early_leave = FALSE THEN 1 ELSE 0 END) as compliant_days,
                    SUM(CASE WHEN ar.is_late = TRUE THEN 1 ELSE 0 END) as late_count,
                    SUM(CASE WHEN ar.is_early_leave = TRUE THEN 1 ELSE 0 END) as early_leave_count,
                    SUM(CASE WHEN ar.status = 'absent' THEN 1 ELSE 0 END) as absent_count,
                    COALESCE(SUM(ar.worked_hours), 0) as total_worked_hours,
                    COALESCE(SUM(ar.expected_hours), 0) as total_expected_hours
                FROM zkteco_attendance_record ar
                WHERE ar.employee_id IS NOT NULL
                GROUP BY ar.employee_id, ar.department_id, ar.employee_branch_id, ar.shift_id
            )
        """ % self._table)


class AttendanceExceptionReport(models.Model):
    """Attendance Exception Report."""
    _name = 'zkteco.exception.report'
    _description = 'Attendance Exception Report'
    _auto = False
    _order = 'date desc, severity desc'

    employee_id = fields.Many2one('hr.employee', string='Employee', readonly=True)
    department_id = fields.Many2one('hr.department', string='Department', readonly=True)
    employee_branch_id = fields.Many2one('zkteco.branch', string='Branch', readonly=True)
    date = fields.Date(string='Date', readonly=True)
    shift_id = fields.Many2one('zkteco.shift', string='Shift', readonly=True)

    exception_type = fields.Selection([
        ('late', 'Late Arrival'),
        ('early_leave', 'Early Departure'),
        ('missed_punch', 'Missed Punch'),
        ('absent', 'Absence'),
        ('excess_overtime', 'Excess Overtime'),
    ], string='Exception Type', readonly=True)

    severity = fields.Selection([
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('critical', 'Critical'),
    ], string='Severity', readonly=True)
    details = fields.Char(string='Details', readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %s AS (
                SELECT
                    ar.id as id,
                    ar.employee_id as employee_id,
                    ar.department_id as department_id,
                    ar.employee_branch_id as employee_branch_id,
                    ar.date as date,
                    ar.shift_id as shift_id,
                    CASE
                        WHEN ar.status = 'absent' THEN 'absent'
                        WHEN ar.status = 'missed_punch' THEN 'missed_punch'
                        WHEN ar.is_late = TRUE THEN 'late'
                        WHEN ar.is_early_leave = TRUE THEN 'early_leave'
                        WHEN ar.overtime_hours > 4.0 THEN 'excess_overtime'
                        ELSE 'late'
                    END as exception_type,
                    CASE
                        WHEN ar.status = 'absent' THEN 'critical'
                        WHEN ar.status = 'missed_punch' THEN 'high'
                        WHEN ar.is_late = TRUE AND ar.late_minutes > 30 THEN 'high'
                        WHEN ar.is_early_leave = TRUE THEN 'medium'
                        ELSE 'low'
                    END as severity,
                    CASE
                        WHEN ar.status = 'absent' THEN 'Employee absent without punch'
                        WHEN ar.status = 'missed_punch' THEN 'Incomplete punch record'
                        WHEN ar.is_late = TRUE THEN 'Late arrival by ' || ar.late_minutes::text || ' mins'
                        WHEN ar.is_early_leave = TRUE THEN 'Early departure by ' || ar.early_leave_minutes::text || ' mins'
                        WHEN ar.overtime_hours > 4.0 THEN 'Overtime recorded: ' || ar.overtime_hours::text || ' hrs'
                        ELSE 'General anomaly'
                    END as details
                FROM zkteco_attendance_record ar
                WHERE ar.employee_id IS NOT NULL AND (
                    ar.status IN ('absent', 'missed_punch') OR
                    ar.is_late = TRUE OR
                    ar.is_early_leave = TRUE OR
                    ar.overtime_hours > 4.0
                )
            )
        """ % self._table)


class DepartmentAttendanceReport(models.Model):
    """Department Attendance Summary / Dashboard Report."""
    _name = 'zkteco.department.attendance.report'
    _description = 'Department Attendance Summary Report'
    _auto = False
    _order = 'attendance_rate desc, department_id'

    department_id = fields.Many2one('hr.department', string='Department', readonly=True)
    total_employees = fields.Integer(string='Total Employees', readonly=True)
    present_count = fields.Integer(string='Present Count', readonly=True)
    absent_count = fields.Integer(string='Absent Count', readonly=True)
    on_leave_count = fields.Integer(string='On Leave Count', readonly=True)
    missed_punch_count = fields.Integer(string='Missed Punch Count', readonly=True)
    late_count = fields.Integer(string='Late Count', readonly=True)
    early_leave_count = fields.Integer(string='Early Departure Count', readonly=True)

    attendance_rate = fields.Float(string='Attendance Rate (%)', readonly=True)
    punctuality_rate = fields.Float(string='Punctuality Rate (%)', readonly=True)
    total_worked_hours = fields.Float(string='Total Worked Hours', readonly=True)
    total_overtime_hours = fields.Float(string='Total Overtime Hours', readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %s AS (
                SELECT
                    COALESCE(ar.department_id, 0) as id,
                    ar.department_id as department_id,
                    COUNT(DISTINCT ar.employee_id) as total_employees,
                    SUM(CASE WHEN ar.status = 'present' THEN 1 ELSE 0 END) as present_count,
                    SUM(CASE WHEN ar.status = 'absent' THEN 1 ELSE 0 END) as absent_count,
                    SUM(CASE WHEN ar.status = 'on_leave' THEN 1 ELSE 0 END) as on_leave_count,
                    SUM(CASE WHEN ar.status = 'missed_punch' THEN 1 ELSE 0 END) as missed_punch_count,
                    SUM(CASE WHEN ar.is_late = TRUE THEN 1 ELSE 0 END) as late_count,
                    SUM(CASE WHEN ar.is_early_leave = TRUE THEN 1 ELSE 0 END) as early_leave_count,
                    CASE
                        WHEN COUNT(ar.id) = 0 THEN 0
                        ELSE (SUM(CASE WHEN ar.status IN ('present', 'on_leave') THEN 1 ELSE 0 END)::float / COUNT(ar.id)::float)
                    END as attendance_rate,
                    CASE
                        WHEN SUM(CASE WHEN ar.status = 'present' THEN 1 ELSE 0 END) = 0 THEN 0
                        ELSE (SUM(CASE WHEN ar.status = 'present' AND ar.is_late = FALSE THEN 1 ELSE 0 END)::float / SUM(CASE WHEN ar.status = 'present' THEN 1 ELSE 0 END)::float)
                    END as punctuality_rate,
                    COALESCE(SUM(ar.worked_hours), 0) as total_worked_hours,
                    COALESCE(SUM(ar.overtime_hours), 0) as total_overtime_hours
                FROM zkteco_attendance_record ar
                GROUP BY ar.department_id
            )
        """ % self._table)


class PayrollAttendanceSummary(models.Model):
    """Payroll Attendance Summary Report."""
    _name = 'zkteco.payroll.attendance.summary'
    _description = 'Payroll Attendance Summary'
    _auto = False
    _order = 'year_month desc, employee_id'

    employee_id = fields.Many2one('hr.employee', string='Employee', readonly=True)
    department_id = fields.Many2one('hr.department', string='Department', readonly=True)
    employee_branch_id = fields.Many2one('zkteco.branch', string='Branch', readonly=True)
    shift_id = fields.Many2one('zkteco.shift', string='Shift', readonly=True)
    year_month = fields.Char(string='Year-Month', readonly=True)
    month_start = fields.Date(string='Month Start', readonly=True)

    total_calendar_days = fields.Integer(string='Records Count', readonly=True)
    present_days = fields.Integer(string='Present Days', readonly=True)
    absent_days = fields.Integer(string='Unexcused Absences', readonly=True)
    on_leave_days = fields.Integer(string='Approved Leave Days', readonly=True)
    paid_leave_days = fields.Float(string='Paid Leave Days', readonly=True)
    unpaid_leave_days = fields.Float(string='Unpaid Leave Days', readonly=True)
    payable_days = fields.Float(string='Payable Days', readonly=True)

    worked_hours = fields.Float(string='Total Worked Hours', readonly=True)
    expected_hours = fields.Float(string='Total Expected Hours', readonly=True)
    overtime_hours = fields.Float(string='Approved Overtime Hours', readonly=True)
    late_minutes = fields.Integer(string='Late Penalty Minutes', readonly=True)
    early_leave_minutes = fields.Integer(string='Early Leave Penalty Minutes', readonly=True)
    unpaid_absence_days = fields.Float(string='Unpaid Absence Days', readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %s AS (
                SELECT
                    (ar.employee_id::text || '_' || TO_CHAR(ar.date, 'YYYYMM') || '_' || COALESCE(ar.shift_id, 0)::text)::text as id,
                    ar.employee_id as employee_id,
                    ar.department_id as department_id,
                    ar.employee_branch_id as employee_branch_id,
                    ar.shift_id as shift_id,
                    TO_CHAR(ar.date, 'YYYY-MM') as year_month,
                    DATE_TRUNC('month', ar.date)::date as month_start,
                    COUNT(ar.id) as total_calendar_days,
                    SUM(CASE WHEN ar.status = 'present' THEN 1 ELSE 0 END) as present_days,
                    SUM(CASE WHEN ar.status = 'absent' THEN 1 ELSE 0 END) as absent_days,
                    SUM(CASE WHEN ar.status = 'on_leave' THEN 1 ELSE 0 END) as on_leave_days,
                    SUM(CASE WHEN ar.status = 'on_leave' AND ar.is_paid_leave = TRUE THEN (CASE WHEN ar.is_half_day_leave = TRUE THEN 0.5 ELSE 1.0 END) ELSE 0 END) as paid_leave_days,
                    SUM(CASE WHEN ar.status = 'on_leave' AND ar.is_paid_leave = FALSE THEN (CASE WHEN ar.is_half_day_leave = TRUE THEN 0.5 ELSE 1.0 END) ELSE 0 END) as unpaid_leave_days,
                    (
                        SUM(CASE WHEN ar.status = 'present' THEN 1 ELSE 0 END) +
                        SUM(CASE WHEN ar.status = 'on_leave' AND ar.is_paid_leave = TRUE THEN (CASE WHEN ar.is_half_day_leave = TRUE THEN 0.5 ELSE 1.0 END) ELSE 0 END)
                    ) as payable_days,
                    COALESCE(SUM(ar.worked_hours), 0) as worked_hours,
                    COALESCE(SUM(ar.expected_hours), 0) as expected_hours,
                    COALESCE(SUM(ar.overtime_hours), 0) as overtime_hours,
                    COALESCE(SUM(ar.late_minutes), 0) as late_minutes,
                    COALESCE(SUM(ar.early_leave_minutes), 0) as early_leave_minutes,
                    (
                        SUM(CASE WHEN ar.status = 'absent' THEN 1 ELSE 0 END) +
                        SUM(CASE WHEN ar.status = 'on_leave' AND ar.is_paid_leave = FALSE THEN (CASE WHEN ar.is_half_day_leave = TRUE THEN 0.5 ELSE 1.0 END) ELSE 0 END)
                    ) as unpaid_absence_days
                FROM zkteco_attendance_record ar
                WHERE ar.employee_id IS NOT NULL
                GROUP BY ar.employee_id, ar.department_id, ar.employee_branch_id, ar.shift_id, TO_CHAR(ar.date, 'YYYYMM'), TO_CHAR(ar.date, 'YYYY-MM'), DATE_TRUNC('month', ar.date)

            )
        """ % self._table)



class AttendanceAuditTrail(models.Model):
    """Attendance Audit Trail Log."""
    _name = 'zkteco.attendance.audit.trail'
    _description = 'Attendance Audit Trail'
    _order = 'timestamp desc'

    name = fields.Char(string='Audit Summary', required=True)
    timestamp = fields.Datetime(string='Timestamp', default=fields.Datetime.now, required=True, index=True)
    employee_id = fields.Many2one('hr.employee', string='Employee', index=True)
    attendance_record_id = fields.Many2one('zkteco.attendance.record', string='Attendance Record', ondelete='set null')
    user_id = fields.Many2one('res.users', string='Done By User', default=lambda self: self.env.user, required=True)
    
    action_type = fields.Selection([
        ('create', 'Record Created'),
        ('write', 'Record Updated'),
        ('manual_present', 'Marked Present'),
        ('manual_absent', 'Marked Absent'),
        ('quarantine_link', 'Quarantine Link'),
        ('status_override', 'Status Overridden'),
    ], string='Action Type', required=True, index=True)

    field_name = fields.Char(string='Field Changed')
    old_value = fields.Text(string='Old Value')
    new_value = fields.Text(string='New Value')
    notes = fields.Text(string='Notes / Rationale')


class BranchAttendanceReport(models.Model):
    """Attendance by Branch / Location Report."""
    _name = 'zkteco.branch.attendance.report'
    _description = 'Attendance by Branch Report'
    _auto = False
    _order = 'branch_id, date desc, employee_id'

    branch_id = fields.Many2one('zkteco.branch', string='Branch', readonly=True)
    employee_id = fields.Many2one('hr.employee', string='Employee', readonly=True)
    department_id = fields.Many2one('hr.department', string='Department', readonly=True)
    date = fields.Date(string='Date', readonly=True)
    status = fields.Selection([
        ('present', 'Present'),
        ('absent', 'Absent'),
        ('missed_punch', 'Missed Punch'),
        ('on_leave', 'On Leave'),
    ], string='Status', readonly=True)
    first_checkin = fields.Datetime(string='Check-In', readonly=True)
    last_checkout = fields.Datetime(string='Check-Out', readonly=True)
    worked_hours = fields.Float(string='Worked Hours', readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %s AS (
                SELECT
                    ar.id as id,
                    ar.employee_branch_id as branch_id,
                    ar.employee_id as employee_id,
                    ar.department_id as department_id,
                    ar.date as date,
                    ar.status as status,
                    ar.first_checkin as first_checkin,
                    ar.last_checkout as last_checkout,
                    COALESCE(ar.worked_hours, 0) as worked_hours
                FROM zkteco_attendance_record ar
                WHERE ar.employee_branch_id IS NOT NULL
            )
        """ % self._table)
