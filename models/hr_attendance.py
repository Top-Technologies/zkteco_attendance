from datetime import datetime, time
import pytz
from odoo import models, fields, api, exceptions, _
from odoo.tools import format_datetime

class HrAttendance(models.Model):
    _inherit = 'hr.attendance'

    shift_id = fields.Many2one('zkteco.shift', string='Assigned Shift')
    is_afternoon_punch = fields.Boolean(string='Afternoon Only Punch', default=False)
    attendance_record_id = fields.Many2one(
        'zkteco.attendance.record',
        string='Daily Attendance Record',
        ondelete='set null',
        index=True,
    )

    @api.constrains('check_in', 'check_out', 'employee_id')
    def _check_validity(self):
        """
        Custom validity constraint for biometric two-punch attendance:
        - Prevents overlapping time slices for the same employee.
        - Allows historical unclosed attendances on previous days (representing missed checkouts).
        - Prevents multiple unclosed attendances on the same local date.
        """
        for attendance in self:
            if not attendance.check_in or not attendance.employee_id:
                continue

            timezone = attendance.employee_id.tz or self.env.user.tz or 'UTC'
            try:
                tz = pytz.timezone(timezone)
            except pytz.UnknownTimeZoneError:
                tz = pytz.UTC

            local_dt = pytz.utc.localize(attendance.check_in).astimezone(tz)
            local_date = local_dt.date()
            start_of_day = tz.localize(datetime.combine(local_date, time.min)).astimezone(pytz.UTC).replace(tzinfo=None)
            end_of_day = tz.localize(datetime.combine(local_date, time.max)).astimezone(pytz.UTC).replace(tzinfo=None)

            # Check if there is another open attendance on the same day
            if not attendance.check_out:
                same_day_open = self.env['hr.attendance'].search([
                    ('employee_id', '=', attendance.employee_id.id),
                    ('check_out', '=', False),
                    ('id', '!=', attendance.id),
                    ('check_in', '>=', start_of_day),
                    ('check_in', '<=', end_of_day),
                ], limit=1)
                if same_day_open:
                    raise exceptions.ValidationError(_(
                        "Cannot create multiple open attendances for %(empl_name)s on the same day.",
                        empl_name=attendance.employee_id.name
                    ))
            else:
                # Check for direct overlap with another attendance having check_in and check_out
                overlap = self.env['hr.attendance'].search([
                    ('employee_id', '=', attendance.employee_id.id),
                    ('id', '!=', attendance.id),
                    ('check_out', '!=', False),
                    ('check_in', '<', attendance.check_out),
                    ('check_out', '>', attendance.check_in),
                ], limit=1)
                if overlap:
                    raise exceptions.ValidationError(_(
                        "Cannot create attendance record for %(empl_name)s because it overlaps with an existing attendance from %(check_in)s to %(check_out)s.",
                        empl_name=attendance.employee_id.name,
                        check_in=format_datetime(self.env, overlap.check_in, dt_format=False),
                        check_out=format_datetime(self.env, overlap.check_out, dt_format=False)
                    ))

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for record in records:
            if record.check_in and record.employee_id:
                # Convert UTC check_in to employee local date if possible
                timezone = record.employee_id.tz or self.env.user.tz or 'UTC'
                try:
                    tz = pytz.timezone(timezone)
                except pytz.UnknownTimeZoneError:
                    tz = pytz.UTC
                    
                local_dt = pytz.utc.localize(record.check_in).astimezone(tz)
                punch_date = local_dt.date()
                
                att_record = self.env['zkteco.attendance.record'].sudo().search([
                    ('employee_id', '=', record.employee_id.id),
                    ('date', '=', punch_date)
                ], limit=1)
                
                if not att_record:
                    # Find shift for this day
                    shift = self.env['zkteco.employee.shift'].sudo().search([
                        ('employee_id', '=', record.employee_id.id),
                        ('date_start', '<=', punch_date),
                        ('date_end', '>=', punch_date),
                    ], limit=1)
                    
                    att_record = self.env['zkteco.attendance.record'].sudo().create({
                        'employee_id': record.employee_id.id,
                        'date': punch_date,
                        'shift_id': shift.shift_id.id if shift else False,
                    })
                
                record.attendance_record_id = att_record.id
                
        return records
