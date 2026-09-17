from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from datetime import timedelta

class AutoRotateShiftWizard(models.TransientModel):
    _name = 'zkteco.auto.rotate.wizard'
    _description = 'Assign Auto-Rotating Shifts'

    employee_ids = fields.Many2many('hr.employee', string='Employees', required=True)
    day_shift_id = fields.Many2one('zkteco.shift', string='Day Shift', required=True)
    night_shift_id = fields.Many2one('zkteco.shift', string='Night Shift', required=True)
    rotation_days = fields.Integer(string='Rotation Period (Days)', default=7, required=True, help="Number of days before flipping between Day and Night shift.")
    start_date = fields.Date(string='Start Date', required=True, default=fields.Date.context_today)
    end_date = fields.Date(string='End Date', required=True)

    @api.constrains('start_date', 'end_date', 'rotation_days')
    def _check_dates(self):
        for record in self:
            if record.start_date > record.end_date:
                raise ValidationError(_("End Date must be after Start Date."))
            if record.rotation_days <= 0:
                raise ValidationError(_("Rotation Period must be greater than 0."))

    def action_apply_rotation(self):
        self.ensure_one()
        
        # We will generate periods of length `rotation_days`
        # Alternating between day_shift_id and night_shift_id
        current_start = self.start_date
        is_day_shift = True
        
        vals_list = []
        
        while current_start <= self.end_date:
            current_end = current_start + timedelta(days=self.rotation_days - 1)
            if current_end > self.end_date:
                current_end = self.end_date
                
            active_shift_id = self.day_shift_id.id if is_day_shift else self.night_shift_id.id
            
            for employee in self.employee_ids:
                vals_list.append({
                    'employee_id': employee.id,
                    'shift_id': active_shift_id,
                    'date_start': current_start,
                    'date_end': current_end,
                })
                
            current_start = current_end + timedelta(days=1)
            is_day_shift = not is_day_shift
            
        if vals_list:
            # Optionally, remove existing overlapping shifts for these employees to avoid unique constraint errors
            existing_shifts = self.env['zkteco.employee.shift'].search([
                ('employee_id', 'in', self.employee_ids.ids),
                '|',
                '&', ('date_start', '<=', self.end_date), ('date_start', '>=', self.start_date),
                '&', ('date_end', '<=', self.end_date), ('date_end', '>=', self.start_date),
            ])
            if existing_shifts:
                existing_shifts.unlink()
                
            self.env['zkteco.employee.shift'].create(vals_list)
            
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Rotation Applied'),
                'message': _('Auto-rotating shift schedule generated for selected employees.'),
                'type': 'success',
                'sticky': False,
            }
        }
