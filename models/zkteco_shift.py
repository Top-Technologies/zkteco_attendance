from odoo import models, fields, api

class ZKTecoShift(models.Model):
    _name = 'zkteco.shift'
    _description = 'ZKTeco Shift Definition'

    name = fields.Char(string='Shift Name', required=True)
    start_time = fields.Float(string='Start Time', required=True, help="Time in decimal hours (e.g., 8.0 for 08:00)")
    end_time = fields.Float(string='End Time', required=True, help="Time in decimal hours (e.g., 17.0 for 17:00)")
    grace_in = fields.Integer(string='Grace In (Mins)', default=0)
    grace_out = fields.Integer(string='Grace Out (Mins)', default=0)
    is_rotating = fields.Boolean(string='Rotating Shift', default=False)
    work_policy_id = fields.Many2one('zkteco.work.policy', string='Work Policy')

    def _get_time_string(self, decimal_time):
        """Convert float hours to HH:MM string."""
        hours = int(decimal_time)
        minutes = int((decimal_time - hours) * 60)
        return f"{hours:02d}:{minutes:02d}"

    @api.depends('name', 'start_time', 'end_time')
    def _compute_display_name(self):
        for rec in self:
            start = self._get_time_string(rec.start_time)
            end = self._get_time_string(rec.end_time)
            rec.display_name = f"{rec.name} ({start} - {end})"

class ZKTecoEmployeeShift(models.Model):
    _name = 'zkteco.employee.shift'
    _description = 'ZKTeco Employee Shift Mapping'

    employee_id = fields.Many2one('hr.employee', string='Employee', required=True, ondelete='cascade')
    shift_id = fields.Many2one('zkteco.shift', string='Shift', required=True, ondelete='cascade')
    date_start = fields.Date(string='Start Date', required=True)
    date_end = fields.Date(string='End Date', required=True)

    _sql_constraints = [
        ('employee_shift_overlap', 'unique(employee_id, date_start)', 'Employee cannot have multiple shifts starting on the same day!')
    ]

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for record in records:
            record._update_attendance_records()
        return records

    def write(self, vals):
        res = super().write(vals)
        for record in self:
            record._update_attendance_records()
        return res

    def unlink(self):
        for record in self:
            attendances = self.env['zkteco.attendance.record'].search([
                ('employee_id', '=', record.employee_id.id),
                ('date', '>=', record.date_start),
                ('date', '<=', record.date_end),
                ('shift_id', '=', record.shift_id.id),
            ])
            if attendances:
                attendances.write({'shift_id': False})
        return super().unlink()

    def _update_attendance_records(self):
        self.ensure_one()
        attendances = self.env['zkteco.attendance.record'].search([
            ('employee_id', '=', self.employee_id.id),
            ('date', '>=', self.date_start),
            ('date', '<=', self.date_end),
        ])
        if attendances:
            attendances.write({'shift_id': self.shift_id.id})
