from odoo import models, fields, tools

class AttendanceAbsenceReport(models.Model):
    _name = 'attendance.absence.report'
    _description = 'Attendance Absence Report'
    _auto = False
    _order = 'date desc, employee_id'

    employee_id = fields.Many2one('hr.employee', string='Employee', readonly=True)
    department_id = fields.Many2one('hr.department', string='Department', readonly=True)
    employee_branch_id = fields.Many2one('zkteco.branch', string='Branch', readonly=True)
    date = fields.Date(string='Date', readonly=True)
    shift_id = fields.Many2one('zkteco.shift', string='Expected Shift', readonly=True)
    remarks = fields.Text(string='Remarks', readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, 'attendance_absence_report')
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW attendance_absence_report AS (
                SELECT
                    ar.id as id,
                    ar.employee_id as employee_id,
                    ar.department_id as department_id,
                    ar.employee_branch_id as employee_branch_id,
                    ar.date as date,
                    ar.shift_id as shift_id,
                    ar.remarks as remarks
                FROM
                    zkteco_attendance_record ar
                WHERE
                    ar.status = 'absent'
            )
        """)

