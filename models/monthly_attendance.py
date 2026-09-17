# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError
import calendar
from datetime import date

class MonthlyAttendance(models.Model):
    _name = 'zkteco.monthly.attendance'
    _description = 'Monthly Attendance Summary'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'year desc, month desc, employee_id'

    name = fields.Char(string='Name', compute='_compute_name', store=True)
    
    employee_id = fields.Many2one('hr.employee', string='Employee', required=True, tracking=True)
    department_id = fields.Many2one('hr.department', related='employee_id.department_id', store=True, string='Department')
    manager_id = fields.Many2one('hr.employee', related='employee_id.parent_id', store=True, string='Manager')
    
    month = fields.Selection([
        ('01', 'January'), ('02', 'February'), ('03', 'March'),
        ('04', 'April'), ('05', 'May'), ('06', 'June'),
        ('07', 'July'), ('08', 'August'), ('09', 'September'),
        ('10', 'October'), ('11', 'November'), ('12', 'December')
    ], string='Month', required=True, default=lambda self: str(date.today().month).zfill(2))
    
    year = fields.Char(string='Year', required=True, default=lambda self: str(date.today().year))
    
    overtime_hours = fields.Float(string='Overtime Hours', tracking=True)
    late_minutes = fields.Integer(string='Late Minutes', tracking=True)
    absent_days = fields.Integer(string='Absent Days', tracking=True)
    
    state = fields.Selection([
        ('draft', 'Draft'),
        ('manager_approve', 'Waiting Manager Approval'),
        ('hr_approve', 'Waiting HR Approval'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected')
    ], string='Status', default='draft', tracking=True, required=True)

    _sql_constraints = [
        ('employee_month_year_uniq', 'unique (employee_id, month, year)', 'A monthly record already exists for this employee for the selected month and year!')
    ]

    @api.depends('employee_id', 'month', 'year')
    def _compute_name(self):
        for record in self:
            if record.employee_id and record.month and record.year:
                month_name = dict(self._fields['month'].selection).get(record.month)
                record.name = f"{record.employee_id.name} - {month_name} {record.year}"
            else:
                record.name = 'New Monthly Record'

    def action_compute(self):
        for record in self:
            if record.state != 'draft':
                raise UserError(_('You can only compute statistics in Draft state.'))
                
            try:
                year = int(record.year)
                month = int(record.month)
                start_date = date(year, month, 1)
                end_date = date(year, month, calendar.monthrange(year, month)[1])
            except ValueError:
                raise UserError(_('Invalid Year or Month format.'))
                
            attendance_records = self.env['zkteco.attendance.record'].search([
                ('employee_id', '=', record.employee_id.id),
                ('date', '>=', start_date),
                ('date', '<=', end_date)
            ])
            
            record.overtime_hours = sum(attendance_records.mapped('overtime_hours'))
            record.late_minutes = sum(attendance_records.mapped('late_minutes'))
            record.absent_days = len(attendance_records.filtered(lambda r: r.status == 'absent'))

    def action_submit(self):
        for record in self:
            record.state = 'manager_approve'
            # Schedule activity for manager without triggering email error
            if record.manager_id and record.manager_id.user_id:
                self.env['mail.activity'].create({
                    'res_id': record.id,
                    'res_model_id': self.env['ir.model']._get('zkteco.monthly.attendance').id,
                    'activity_type_id': self.env.ref('mail.mail_activity_data_todo').id,
                    'summary': 'Please approve the monthly attendance.',
                    'note': 'Please approve the monthly attendance for %s.' % record.employee_id.name,
                    'user_id': record.manager_id.user_id.id,
                })

    def action_manager_approve(self):
        for record in self:
            # Optionally check if user is manager or HR
            if not self.env.user.has_group('hr.group_hr_user') and record.manager_id.user_id != self.env.user:
                raise UserError(_("Only the employee's manager or HR can approve this."))
                
            record.state = 'hr_approve'
            # Mark manager activities as done
            record.activity_feedback(['mail.mail_activity_data_todo'])
            
            # Find HR users to notify (those in hr.group_hr_manager or hr.group_hr_user)
            hr_users = self.env.ref('hr.group_hr_user').users
            for hr_user in hr_users:
                self.env['mail.activity'].create({
                    'res_id': record.id,
                    'res_model_id': self.env['ir.model']._get('zkteco.monthly.attendance').id,
                    'activity_type_id': self.env.ref('mail.mail_activity_data_todo').id,
                    'summary': 'Final HR Approval Required',
                    'note': 'Manager approved. Please provide final HR approval for %s.' % record.employee_id.name,
                    'user_id': hr_user.id,
                })

    def action_hr_approve(self):
        for record in self:
            record.state = 'approved'
            record.activity_feedback(['mail.mail_activity_data_todo'])

    def action_reject(self):
        for record in self:
            record.state = 'rejected'
            record.activity_feedback(['mail.mail_activity_data_todo'])
            
    def action_set_to_draft(self):
        for record in self:
            record.state = 'draft'
            record.activity_unlink(['mail.mail_activity_data_todo'])

    @api.model
    def _cron_generate_monthly_attendance(self):
        """Automatically generate Monthly Attendance records for the current month for all active employees"""
        today = date.today()
        current_year = str(today.year)
        current_month = str(today.month).zfill(2)

        employees = self.env['hr.employee'].search([])
        
        for employee in employees:
            # Check if record exists
            existing_record = self.search([
                ('employee_id', '=', employee.id),
                ('month', '=', current_month),
                ('year', '=', current_year)
            ], limit=1)
            
            if not existing_record:
                # Create the record in draft state
                existing_record = self.create({
                    'employee_id': employee.id,
                    'month': current_month,
                    'year': current_year,
                    'state': 'draft'
                })
                
        # Now find all draft records for the current month and recompute them
        draft_records = self.search([
            ('month', '=', current_month),
            ('year', '=', current_year),
            ('state', '=', 'draft')
        ])
        if draft_records:
            draft_records.action_compute()
