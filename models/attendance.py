from odoo import models, fields, api
from odoo.exceptions import UserError
import logging
from datetime import datetime, time, timedelta
import pytz

_logger = logging.getLogger(__name__)

class ZKTecoAttendance(models.Model):
    _name = 'zkteco.attendance'
    _description = 'ZKTeco Attendance Log'
    _order = 'timestamp desc'

    device_id = fields.Many2one('zkteco.device', string='Device', required=True)
    device_branch_id = fields.Many2one('zkteco.branch', related='device_id.branch_id', store=True, string='Device Branch')
    device_user_id = fields.Char(string='Device User ID', required=True, index=True)
    timestamp = fields.Datetime(string='Timestamp', required=True)
    punch_date = fields.Date(string='Punch Date', compute='_compute_punch_date', store=True)
    event_type = fields.Integer(string='Event Type')

    raw_data = fields.Text(string='Raw Data')
    state = fields.Selection([
        ('draft', 'Draft'),
        ('processed', 'Processed'),
        ('error', 'Error')
    ], string='Status', default='draft', index=True)
    employee_id = fields.Many2one('hr.employee', string='Employee')
    error_message = fields.Text(string='Error Message')

    # Employee History Metrics (Computed for the form view)
    emp_present_days = fields.Integer(string='Present Days', compute='_compute_emp_history')
    emp_absent_days = fields.Integer(string='Absent Days', compute='_compute_emp_history')
    emp_worked_hours = fields.Float(string='Total Worked Hours', compute='_compute_emp_history')
    emp_overtime_hours = fields.Float(string='Total Overtime', compute='_compute_emp_history')
    
    daily_status = fields.Selection([
        ('present', 'Present'),
        ('absent', 'Absent'),
        ('missed_punch', 'Incomplete'),
        ('on_leave', 'On Leave'),
    ], string='Attendance Status', compute='_compute_daily_status')

    @api.depends('employee_id', 'punch_date')
    def _compute_daily_status(self):
        for log in self:
            if not log.employee_id or not log.punch_date:
                log.daily_status = False
                continue
            
            record = self.env['zkteco.attendance.record'].search([
                ('employee_id', '=', log.employee_id.id),
                ('date', '=', log.punch_date)
            ], limit=1)
            
            if record:
                log.daily_status = record.status
            else:
                log.daily_status = False

    @api.depends('employee_id')
    def _compute_emp_history(self):
        for log in self:
            if not log.employee_id:
                log.emp_present_days = 0
                log.emp_absent_days = 0
                log.emp_worked_hours = 0.0
                log.emp_overtime_hours = 0.0
                continue
                
            records = self.env['zkteco.attendance.record'].search([('employee_id', '=', log.employee_id.id)])
            log.emp_present_days = len(records.filtered(lambda r: r.status in ['present', 'on_leave']))
            log.emp_absent_days = len(records.filtered(lambda r: r.status == 'absent'))
            log.emp_worked_hours = sum(records.mapped('worked_hours'))
            log.emp_overtime_hours = sum(records.mapped('overtime_hours'))

    def _compute_punch_date(self):
        for log in self:
            log.punch_date = log.timestamp.date() if log.timestamp else False

    def action_process_logs(self):
        """Processes draft logs and creates hr.attendance records in batches."""
        batch_size = 100
        while True:
            draft_logs = self.search([('state', '=', 'draft')], order='timestamp asc', limit=batch_size)
            if not draft_logs:
                break

            # PRE-CACHE MAPPINGS
            device_user_ids = draft_logs.mapped('device_user_id')
            device_ids = draft_logs.mapped('device_id.id')
            mappings = self.env['zkteco.user.mapping'].search([
                ('device_user_id', 'in', device_user_ids),
                ('device_id', 'in', device_ids)
            ])
            mapping_cache = {(m.device_user_id, m.device_id.id): m.employee_id for m in mappings if m.employee_id}

            # PRE-CACHE SHIFTS
            min_date = min([l.timestamp.date() for l in draft_logs if l.timestamp])
            max_date = max([l.timestamp.date() for l in draft_logs if l.timestamp])
            employee_ids = [emp.id for emp in mapping_cache.values()]
            
            shifts_cache = self.env['zkteco.employee.shift'].sudo().search([
                ('employee_id', 'in', employee_ids),
                ('date_start', '<=', max_date),
                ('date_end', '>=', min_date),
            ])

            for log in draft_logs:
                try:
                    with self.env.cr.savepoint():
                        employee = mapping_cache.get((log.device_user_id, log.device_id.id))

                        if not employee:
                            log.write({
                                'state': 'error',
                                'error_message': f'No valid employee mapping found for Device User ID {log.device_user_id}'
                            })
                            continue

                        log.employee_id = employee

                        # 2. Create or update hr.attendance record
                        self._create_or_update_hr_attendance(employee, log.timestamp, shifts_cache)
                        log.write({
                            'state': 'processed',
                            'error_message': False
                        })
                except Exception as e:
                    _logger.error(f"Error processing ZKTeco log {log.id}: {str(e)}")
                    try:
                        with self.env.cr.savepoint():
                            log.write({
                                'state': 'error',
                                'error_message': str(e)
                            })
                    except Exception as inner_e:
                        _logger.critical(f"Failed to write error state for log {log.id}: {inner_e}")

    def _create_or_update_hr_attendance(self, employee, timestamp, shifts_cache):
        """Helper to integrate with Odoo's standard hr.attendance following two-punch logic."""
        attendance_obj = self.env['hr.attendance']

        # 1. 30-Second Rapid Punch De-duplication
        time_min = timestamp - timedelta(seconds=30)
        time_max = timestamp + timedelta(seconds=30)
        duplicate = attendance_obj.search([
            ('employee_id', '=', employee.id),
            '|',
            '&', ('check_in', '>=', time_min), ('check_in', '<=', time_max),
            '&', ('check_out', '>=', time_min), ('check_out', '<=', time_max)
        ], limit=1)

        if duplicate:
            _logger.info("Rapid duplicate punch detected for employee %s at %s (within +/- 30s). Skipping.", employee.name, timestamp)
            return

        # 2. Determine local time and shift midpoint
        timezone = employee.tz or self.env.user.tz or 'UTC'
        try:
            tz = pytz.timezone(timezone)
        except pytz.UnknownTimeZoneError:
            tz = pytz.UTC

        local_dt = pytz.utc.localize(timestamp).astimezone(tz)
        local_date = local_dt.date()
        local_hour = local_dt.hour + local_dt.minute / 60.0 + local_dt.second / 3600.0

        # Find active shift for this employee on this date from cache
        shift = shifts_cache.filtered(lambda s: s.employee_id.id == employee.id and s.date_start <= local_date <= s.date_end)
        shift_rec = shift[0].shift_id if shift else False
        shift_id = shift_rec.id if shift_rec else False

        # Compute midpoint between shift start and end (defaults to 12:30 PM if not specified)
        midpoint = 12.5
        if shift_rec and shift_rec.start_time is not None and shift_rec.end_time is not None:
            if shift_rec.end_time > shift_rec.start_time:
                midpoint = shift_rec.start_time + (shift_rec.end_time - shift_rec.start_time) / 2.0
            else:
                # Night shift crossing midnight
                span = (shift_rec.end_time + 24.0) - shift_rec.start_time
                midpoint = (shift_rec.start_time + span / 2.0) % 24.0

        if shift_rec and shift_rec.end_time < shift_rec.start_time:
            is_afternoon = not (shift_rec.start_time <= local_hour or local_hour < midpoint)
        else:
            is_afternoon = (local_hour >= midpoint)

        # 3. Search for existing attendance record on this local date
        start_utc = tz.localize(datetime.combine(local_date, time.min)).astimezone(pytz.UTC).replace(tzinfo=None)
        end_utc = tz.localize(datetime.combine(local_date, time.max)).astimezone(pytz.UTC).replace(tzinfo=None)

        existing_attendance = attendance_obj.search([
            ('employee_id', '=', employee.id),
            '|',
            ('attendance_record_id.date', '=', local_date),
            '&', ('check_in', '>=', start_utc), ('check_in', '<=', end_utc),
        ], order='check_in asc', limit=1)

        if not existing_attendance:
            if not is_afternoon:
                # Morning check-in punch
                attendance_obj.create({
                    'employee_id': employee.id,
                    'check_in': timestamp,
                    'check_out': False,
                    'is_afternoon_punch': False,
                    'shift_id': shift_id,
                })
            else:
                # Afternoon-only punch (employee missed morning check-in)
                attendance_obj.create({
                    'employee_id': employee.id,
                    'check_in': timestamp,
                    'check_out': timestamp,
                    'is_afternoon_punch': True,
                    'shift_id': shift_id,
                })
        else:
            if existing_attendance.is_afternoon_punch:
                if not is_afternoon:
                    # Morning check-in arrived (out-of-order or delayed sync)
                    existing_attendance.write({
                        'check_in': timestamp,
                        'is_afternoon_punch': False,
                        'shift_id': shift_id or existing_attendance.shift_id,
                    })
                else:
                    # Subsequent afternoon punch: update checkout time
                    existing_attendance.write({
                        'check_in': timestamp,
                        'check_out': timestamp,
                        'shift_id': shift_id or existing_attendance.shift_id,
                    })
            else:
                if is_afternoon:
                    # Afternoon checkout punch (2nd punch or 3rd/4th subsequent punch)
                    # Automatically updates checkout time to the latest punch
                    existing_attendance.write({
                        'check_out': timestamp,
                        'shift_id': shift_id or existing_attendance.shift_id,
                    })
                else:
                    # Multiple punches in the morning: keep earliest arrival as check-in
                    if timestamp < existing_attendance.check_in:
                        existing_attendance.write({
                            'check_in': timestamp,
                            'shift_id': shift_id or existing_attendance.shift_id,
                        })


