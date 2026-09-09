from datetime import datetime, time
from odoo import models, fields, api, _

class ManualPresentWizard(models.TransientModel):
    """Wizard to conditionally mark multiple employees as Present during power outages or exceptions."""
    _name = 'zkteco.manual.present.wizard'
    _description = 'Conditional Mass Present Marking Wizard'

    record_ids = fields.Many2many(
        'zkteco.attendance.record',
        string='Selected Attendance Records'
    )
    
    reason_type = fields.Selection([
        ('power_outage', 'Power Outage'),
        ('device_failure', 'Device Maintenance / Hardware Failure'),
        ('network_down', 'Network Outage'),
        ('other', 'Other Special Condition'),
    ], string='Reason Type', required=True, default='power_outage')
    
    reason_details = fields.Char(
        string='Reason Details / Notes',
        help='Additional explanatory notes for HR audit trail'
    )
    
    grant_full_hours = fields.Boolean(
        string='Grant Full Shift Worked Hours',
        default=True,
        help='Automatically credit the employee with full expected shift hours'
    )

    @api.model
    def default_get(self, fields_list):
        res = super(ManualPresentWizard, self).default_get(fields_list)
        active_ids = self._context.get('active_ids', [])
        if active_ids and 'record_ids' in fields_list:
            res['record_ids'] = [(6, 0, active_ids)]
        return res

    def action_apply_bulk_present(self):
        """Apply present status, credit full worked hours, and log audit trail."""
        self.ensure_one()
        if not self.record_ids:
            return {'type': 'ir.actions.act_window_close'}

        reason_labels = dict(self._fields['reason_type'].selection)
        reason_title = reason_labels.get(self.reason_type, 'Conditional Override')
        reason_str = f"{reason_title}: {self.reason_details}" if self.reason_details else reason_title

        for record in self.record_ids:
            old_status = record.status
            record.status = 'present'
            
            if self.grant_full_hours:
                hours_to_grant = record.expected_hours or 8.0
                record.worked_hours = hours_to_grant
            
            record.is_late = False
            record.is_early_leave = False
            record.late_minutes = 0
            record.early_leave_minutes = 0
            record.remarks = f"Conditional Present ({reason_str})"

            if record.total_punches == 0:
                # Default to 08:00 to 17:00 (9 hours total, minus 1 hour lunch = 8 hours worked)
                start_hour = int(record.shift_start) if record.shift_id and record.shift_start else 8
                end_hour = int(record.shift_end) if record.shift_id and record.shift_end else 17
                
                import pytz
                tz_name = record.employee_id.tz or self.env.user.tz or 'UTC'
                try:
                    local_tz = pytz.timezone(tz_name)
                except pytz.UnknownTimeZoneError:
                    local_tz = pytz.UTC
                    
                check_in_naive = datetime.combine(record.date, time(start_hour, 0))
                check_out_naive = datetime.combine(record.date, time(end_hour, 0))
                
                check_in_dt = local_tz.localize(check_in_naive).astimezone(pytz.UTC).replace(tzinfo=None)
                check_out_dt = local_tz.localize(check_out_naive).astimezone(pytz.UTC).replace(tzinfo=None)
                
                # Check for overlapping records to prevent Odoo ValidationError
                overlapping = self.env['hr.attendance'].search([
                    ('employee_id', '=', record.employee_id.id),
                    '|',
                    '&', ('check_in', '<=', check_out_dt), ('check_out', '>=', check_in_dt),
                    '&', ('check_in', '<=', check_out_dt), ('check_out', '=', False)
                ], limit=1)
                
                if overlapping:
                    # If an overlapping record exists, link it to this daily record instead of creating a new one
                    if not overlapping.attendance_record_id:
                        overlapping.attendance_record_id = record.id
                else:
                    self.env['hr.attendance'].create({
                        'employee_id': record.employee_id.id,
                        'check_in': check_in_dt,
                        'check_out': check_out_dt,
                        'attendance_record_id': record.id,
                    })

            self.env['zkteco.attendance.audit.trail'].create({
                'name': f"Conditional Present ({reason_title}): {record.employee_id.name}",
                'employee_id': record.employee_id.id,
                'attendance_record_id': record.id,
                'user_id': self.env.uid,
                'action_type': 'manual_present',
                'old_value': str(old_status),
                'new_value': 'present',
                'notes': f"Mass conditional update: {reason_str}"
            })

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Conditional Mass Present Applied'),
                'message': _('Successfully marked %s employee(s) as Present (%s).') % (len(self.record_ids), reason_title),
                'type': 'success',
                'sticky': False,
            }
        }
