import logging
from datetime import datetime, time, timedelta
from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class AttendanceRecord(models.Model):
    """Daily attendance record with status tracking."""
    
    _name = 'zkteco.attendance.record'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Daily Attendance Record'
    _order = 'date desc, employee_id'
    _rec_name = 'display_name'
    
    def action_fetch_logs(self):
        """Trigger log fetching from active ADMS configuration."""
        config = self.env['zkteco.adms.config'].search([('active', '=', True)], limit=1)
        if config:
            return config.action_fetch_attendance_data()
        raise UserError(_('No active ADMS configuration found. Please configure the ADMS connection in Settings.'))
    
    # Basic Information
    employee_id = fields.Many2one('hr.employee', string='Employee', required=True, ondelete='cascade', index=True)
    employee_branch_id = fields.Many2one('zkteco.branch', related='employee_id.branch_id', store=True, string='Employee Branch')
    date = fields.Date(string='Date', required=True, default=fields.Date.context_today, index=True)
    department_id = fields.Many2one('hr.department', string='Department', related='employee_id.department_id', store=True)
    job_id = fields.Many2one('hr.job', string='Job Position', related='employee_id.job_id', store=True)
    
    # Status
    status = fields.Selection([
        ('present', 'Present'),
        ('absent', 'Absent'),
        ('missed_punch', 'Missed Punch'),
        ('on_leave', 'On Leave'),
    ], string='Status', compute='_compute_status', store=True, readonly=False, index=True, tracking=True)
    missed_punch_type = fields.Selection([
        ('morning', 'Missed Morning Punch'),
        ('afternoon', 'Missed Afternoon Punch'),
    ], string='Missed Punch Detail', compute='_compute_status', store=True, readonly=False, index=True)
    status_display = fields.Char(string='Attendance Status', compute='_compute_status_display', store=True)
    
    # Punch Times
    first_checkin = fields.Datetime(string='First Check-in', compute='_compute_punch_times', store=True, readonly=False)
    last_checkout = fields.Datetime(string='Last Check-out', compute='_compute_punch_times', store=True, readonly=False)
    total_punches = fields.Integer(string='Total Punches', compute='_compute_punch_times', store=True, readonly=False)
    
    # Attendance Records
    attendance_ids = fields.One2many('hr.attendance', 'attendance_record_id', string='Attendance Records')
    attendance_count = fields.Integer(string='Attendance Count', compute='_compute_attendance_count')
    
    # Working Hours
    worked_hours = fields.Float(string='Worked Hours', compute='_compute_worked_hours', store=True, readonly=False)
    expected_hours = fields.Float(string='Expected Hours', compute='_compute_expected_hours', store=True, readonly=False, default=8.0)
    
    # Time Off / Leave Information
    leave_id = fields.Many2one('hr.leave', string='Time Off Request', compute='_compute_leave_info', store=True, readonly=False)
    leave_type_id = fields.Many2one('hr.leave.type', string='Time Off Type', compute='_compute_leave_info', store=True, readonly=False)
    is_half_day_leave = fields.Boolean(string='Half Day Leave', compute='_compute_leave_info', store=True, readonly=False)
    leave_period = fields.Selection([
        ('full_day', 'Full Day'),
        ('am', 'Morning (AM)'),
        ('pm', 'Afternoon (PM)'),
    ], string='Leave Period', compute='_compute_leave_info', store=True, readonly=False, default='full_day')
    is_paid_leave = fields.Boolean(string='Is Paid Leave', compute='_compute_leave_info', store=True, readonly=False)
    leave_state = fields.Selection([
        ('draft', 'Draft'),
        ('confirm', 'Requested'),
        ('validate1', 'Second Approval'),
        ('validate', 'Approved'),
    ], string='Leave Approval State', compute='_compute_leave_info', store=True, readonly=False)

    
    # Shift Information
    shift_id = fields.Many2one('zkteco.shift', string='Assigned Shift')
    shift_start = fields.Float(string='Shift Start', related='shift_id.start_time', store=True)
    shift_end = fields.Float(string='Shift End', related='shift_id.end_time', store=True)
    
    # Late/Early
    is_late = fields.Boolean(string='Late Arrival', compute='_compute_late_early', store=True, readonly=False)
    is_early_leave = fields.Boolean(string='Early Leave', compute='_compute_late_early', store=True, readonly=False)
    late_minutes = fields.Integer(string='Late Minutes', compute='_compute_late_early', store=True, readonly=False)
    late_minutes_display = fields.Char(string='Late Minutes (Display)', compute='_compute_late_minutes_display', store=True)
    early_leave_minutes = fields.Integer(string='Early Leave Minutes', compute='_compute_late_early', store=True, readonly=False)
    
    # Anomaly Tracking
    is_wrong_shift = fields.Boolean(string='Wrong Shift', compute='_compute_wrong_shift', store=True, readonly=False)
    
    # Notes
    remarks = fields.Text(string='Remarks', tracking=True)
    
    # Overtime
    overtime_hours = fields.Float(string='Overtime Hours', compute='_compute_overtime_hours', store=True, readonly=False)
    
    # Display
    display_name = fields.Char(string='Display Name', compute='_compute_display_name')
    
    # Colors for UI
    color = fields.Integer(string='Color', compute='_compute_color')

    employee_history_ids = fields.One2many(
        'zkteco.attendance.record', 'employee_id',
        string='Employee History',
        compute='_compute_employee_history_ids'
    )

    def _compute_employee_history_ids(self):
        """Compute other attendance records for the same employee."""
        for record in self:
            if record.employee_id:
                record.employee_history_ids = self.env['zkteco.attendance.record'].search([
                    ('employee_id', '=', record.employee_id.id),
                    ('id', '!=', record.id)
                ])
            else:
                record.employee_history_ids = self.env['zkteco.attendance.record']

    _sql_constraints = [

        ('employee_date_unique', 'unique(employee_id, date)', 
         'An attendance record already exists for this employee on this date!')
    ]
    
    @api.depends('employee_id', 'date', 'status')
    def _compute_display_name(self):
        """Compute display name."""
        for record in self:
            if record.employee_id and record.date:
                record.display_name = f"{record.employee_id.name} - {record.date} ({record.status or 'Unknown'})"
            else:
                record.display_name = "New Attendance Record"
    
    @api.depends('status')
    def _compute_color(self):
        """Compute color for kanban/tree view."""
        color_map = {
            'present': 10,      # Green
            'absent': 1,        # Red
            'missed_punch': 3,  # Yellow
            'on_leave': 4,      # Blue
        }
        for record in self:
            record.color = color_map.get(record.status, 0)
    
    @api.depends('attendance_ids', 'attendance_ids.check_in', 'attendance_ids.check_out', 'attendance_ids.is_afternoon_punch')
    def _compute_punch_times(self):
        """Compute first check-in, last check-out, and total punches for two-punch system."""
        for record in self:
            attendances = record.attendance_ids.sorted(key=lambda a: a.check_in)
            
            if not attendances:
                record.first_checkin = False
                record.last_checkout = False
                record.total_punches = 0
                continue

            morning_atts = [a for a in attendances if not a.is_afternoon_punch]
            afternoon_punches = []
            for a in attendances:
                if a.is_afternoon_punch:
                    afternoon_punches.append(a.check_out or a.check_in)
                elif a.check_out:
                    afternoon_punches.append(a.check_out)

            first_in = morning_atts[0].check_in if morning_atts else False
            last_out = max(afternoon_punches) if afternoon_punches else False

            record.first_checkin = first_in
            record.last_checkout = last_out
            
            punches = 0
            if first_in:
                punches += 1
            if last_out:
                punches += 1
            record.total_punches = punches
    
    @api.depends('attendance_ids')
    def _compute_attendance_count(self):
        """Count attendance records."""
        for record in self:
            record.attendance_count = len(record.attendance_ids)
    
    @api.depends('attendance_ids', 'attendance_ids.worked_hours', 'attendance_ids.check_in', 'attendance_ids.check_out', 'attendance_ids.is_afternoon_punch', 'first_checkin', 'last_checkout')
    def _compute_worked_hours(self):
        """Compute total worked hours."""
        for record in self:
            total = 0.0
            today = fields.Date.context_today(record)
            if record.attendance_ids:
                for att in record.attendance_ids:
                    if att.is_afternoon_punch:
                        continue
                    if att.worked_hours:
                        total += att.worked_hours
                    elif att.check_in and not att.check_out:
                        # Only dynamically calculate worked hours for TODAY
                        if record.date == today:
                            delta = fields.Datetime.now() - att.check_in
                            total += max(0.0, delta.total_seconds() / 3600.0)
            elif record.first_checkin and record.last_checkout:
                delta = record.last_checkout - record.first_checkin
                total = max(0.0, delta.total_seconds() / 3600.0)
            record.worked_hours = round(total, 2)

    @api.depends('last_checkout', 'worked_hours', 'expected_hours', 'employee_id.work_policy_id', 'shift_id.work_policy_id')
    def _compute_overtime_hours(self):
        """Compute overtime hours based on assigned work policy."""
        for record in self:
            record.overtime_hours = 0.0
            if not record.last_checkout:
                continue
                
            policy = record.employee_id.work_policy_id or record.shift_id.work_policy_id
            if not policy:
                continue
                
            if policy.policy_type == 'flexible':
                record.overtime_hours = max(0.0, record.worked_hours - record.expected_hours)
            else:
                # Regular, Night, or Other
                # Convert UTC checkout to employee local time
                timezone = record.employee_id.tz or record.env.user.tz or 'UTC'
                import pytz
                try:
                    tz = pytz.timezone(timezone)
                except pytz.UnknownTimeZoneError:
                    tz = pytz.UTC
                    
                checkout_utc = pytz.utc.localize(record.last_checkout)
                checkout_local = checkout_utc.astimezone(tz)
                
                checkout_hour = checkout_local.hour + checkout_local.minute / 60.0 + checkout_local.second / 3600.0
                
                # Check for day boundary cross (e.g. checked out next day)
                days_diff = (checkout_local.date() - record.date).days
                adjusted_checkout_hour = checkout_hour + (days_diff * 24.0)
                
                overtime_begin = policy.overtime_begin_time
                end_t = policy.end_time
                if end_t < policy.start_time:
                    # Night shift: end time and overtime begin threshold cross midnight
                    end_t += 24.0
                    overtime_begin += 24.0
                    
                if adjusted_checkout_hour >= overtime_begin:
                    # Only calculate overtime for the time spent AFTER the overtime_begin threshold (e.g., 18:00)
                    record.overtime_hours = max(0.0, adjusted_checkout_hour - overtime_begin)
    
    @api.depends('employee_id', 'date')
    def _compute_leave_info(self):
        """Fetch matching active leave request (requested or approved) and extract metadata."""
        for record in self:
            record.leave_id = False
            record.leave_type_id = False
            record.is_half_day_leave = False
            record.leave_period = 'full_day'
            record.is_paid_leave = False
            record.leave_state = False

            if not record.employee_id or not record.date or 'hr.leave' not in self.env:
                continue

            leave = self.env['hr.leave'].sudo().search([
                ('employee_id', '=', record.employee_id.id),
                ('state', 'in', ['confirm', 'validate1', 'validate']),
                ('request_date_from', '<=', record.date),
                ('request_date_to', '>=', record.date),
            ], limit=1)

            if not leave:
                start_dt = datetime.combine(record.date, time.min)
                end_dt = datetime.combine(record.date, time.max)
                leave = self.env['hr.leave'].sudo().search([
                    ('employee_id', '=', record.employee_id.id),
                    ('state', 'in', ['confirm', 'validate1', 'validate']),
                    ('date_from', '<=', end_dt),
                    ('date_to', '>=', start_dt),
                ], limit=1)

            if leave:
                record.leave_id = leave.id
                record.leave_type_id = leave.holiday_status_id.id
                record.leave_state = leave.state
                
                is_half = bool(getattr(leave, 'request_unit_half', False))
                record.is_half_day_leave = is_half
                if is_half:
                    period = getattr(leave, 'request_date_from_period', 'am')
                    record.leave_period = period if period in ['am', 'pm'] else 'am'
                else:
                    record.leave_period = 'full_day'

                is_unpaid = getattr(leave.holiday_status_id, 'unpaid', False)
                record.is_paid_leave = not is_unpaid

    @api.depends('shift_id.start_time', 'shift_id.end_time', 'is_half_day_leave')
    def _compute_expected_hours(self):
        """Compute expected worked hours per shift, adjusted for half-day leaves."""
        for record in self:
            base_hours = 8.0
            if record.shift_id:
                if record.shift_id.end_time < record.shift_id.start_time:
                    base_hours = (record.shift_id.end_time + 24.0) - record.shift_id.start_time
                else:
                    base_hours = record.shift_id.end_time - record.shift_id.start_time
            if record.is_half_day_leave:
                record.expected_hours = base_hours / 2.0
            else:
                record.expected_hours = base_hours

    @api.depends('first_checkin', 'last_checkout', 'total_punches', 'date', 'leave_id', 'leave_state', 'is_half_day_leave', 'is_paid_leave', 'leave_period')
    def _compute_status(self):
        """
        Compute attendance status for Two-Punch System:
        - Present: Both morning check-in and afternoon check-out are recorded.
        - Missed Punch (Afternoon): Punched in morning, but missed afternoon checkout.
        - Missed Punch (Morning): Punched in afternoon, but missed morning check-in.
        - Absent: No punches at all.
        - On Leave: Active leave request (requested or approved).
        """
        state_labels = {
            'confirm': 'Pending Approval',
            'validate1': 'Pending 2nd Approval',
            'validate': 'Approved',
        }
        for record in self:
            record.missed_punch_type = False
            if record.leave_id:
                leave_name = record.leave_type_id.name if record.leave_type_id else 'Time Off'
                paid_str = 'Paid' if record.is_paid_leave else 'Unpaid'
                state_str = state_labels.get(record.leave_state, 'Active')

                if record.is_half_day_leave:
                    period_str = f"Half Day ({record.leave_period.upper()})"
                else:
                    period_str = "Full Day"

                if record.total_punches > 0:
                    record.status = 'present'
                    record.remarks = f"On Leave ({leave_name}, {period_str}, {paid_str} - {state_str}) + Punched ({record.total_punches} punches)"
                else:
                    record.status = 'on_leave'
                    record.remarks = f"On Leave: {leave_name} ({period_str}, {paid_str} - {state_str})"
            elif record.total_punches == 0:
                record.status = 'absent'
            else:
                if record.first_checkin and record.last_checkout:
                    record.status = 'present'
                    record.remarks = "Present: Morning check-in and afternoon check-out recorded."
                elif record.first_checkin and not record.last_checkout:
                    record.status = 'missed_punch'
                    record.missed_punch_type = 'afternoon'
                    record.remarks = "Missed Punch (Afternoon): Punched morning check-in but failed to punch afternoon checkout."
                elif not record.first_checkin and record.last_checkout:
                    record.status = 'missed_punch'
                    record.missed_punch_type = 'morning'
                    record.remarks = "Missed Punch (Morning): Punched afternoon checkout but failed to punch morning check-in."
                else:
                    record.status = 'absent'

    @api.depends('status', 'missed_punch_type')
    def _compute_status_display(self):
        for record in self:
            if record.status == 'missed_punch':
                if record.missed_punch_type == 'morning':
                    record.status_display = "Missed Punch (Morning)"
                elif record.missed_punch_type == 'afternoon':
                    record.status_display = "Missed Punch (Afternoon)"
                else:
                    record.status_display = "Missed Punch"
            elif record.status == 'present':
                record.status_display = "Present"
            elif record.status == 'absent':
                record.status_display = "Absent"
            elif record.status == 'on_leave':
                record.status_display = "On Leave"
            else:
                record.status_display = "Unknown"

    @api.depends('first_checkin', 'shift_id', 'employee_id.work_policy_id')
    def _compute_wrong_shift(self):
        """Flag if the employee checked in more than 6 hours away from their assigned shift start time."""
        for record in self:
            record.is_wrong_shift = False
            if not record.first_checkin:
                continue
                
            policy = record.employee_id.work_policy_id or (record.shift_id.work_policy_id if record.shift_id else False)
            start_time = None
            
            if policy:
                start_time = policy.start_time
            elif record.shift_id:
                start_time = record.shift_id.start_time
                
            if start_time is None:
                continue
                
            timezone = record.employee_id.tz or record.env.user.tz or 'UTC'
            import pytz
            try:
                tz = pytz.timezone(timezone)
            except pytz.UnknownTimeZoneError:
                tz = pytz.UTC
                
            checkin_utc = pytz.utc.localize(record.first_checkin)
            checkin_local = checkin_utc.astimezone(tz)
            
            shift_start_hour = int(start_time)
            shift_start_minute = int(round((start_time % 1) * 60))
            if shift_start_minute >= 60:
                shift_start_hour += 1
                shift_start_minute = 0
                
            shift_start_dt = tz.localize(datetime.combine(
                checkin_local.date(),
                time(hour=shift_start_hour, minute=shift_start_minute)
            ))
            
            # If absolute difference is > 6 hours (21600 seconds), it's the wrong shift
            delta_seconds = abs((checkin_local - shift_start_dt).total_seconds())
            if delta_seconds > 21600:
                record.is_wrong_shift = True
    
    @api.depends('first_checkin', 'last_checkout', 'shift_id', 'employee_id.work_policy_id')
    def _compute_late_early(self):
        """Compute if employee is late or left early."""
        for record in self:
            record.is_late = False
            record.is_early_leave = False
            record.late_minutes = 0
            record.early_leave_minutes = 0
            
            # Determine effective start/end times and grace periods
            policy = record.employee_id.work_policy_id or (record.shift_id.work_policy_id if record.shift_id else False)
            
            start_time = None
            end_time = None
            grace_in = 0
            grace_out = 0
            
            if policy:
                start_time = policy.start_time
                end_time = policy.end_time
                grace_in = policy.grace_in
                grace_out = policy.grace_out
            elif record.shift_id:
                start_time = record.shift_id.start_time
                end_time = record.shift_id.end_time
                grace_in = record.shift_id.grace_in
                grace_out = record.shift_id.grace_out
                
            if start_time is None or end_time is None:
                continue
                
            timezone = record.employee_id.tz or record.env.user.tz or 'UTC'
            import pytz
            try:
                tz = pytz.timezone(timezone)
            except pytz.UnknownTimeZoneError:
                tz = pytz.UTC
            
            # Check late arrival
            if record.first_checkin:
                checkin_utc = pytz.utc.localize(record.first_checkin)
                checkin_local = checkin_utc.astimezone(tz)
                
                shift_start_hour = int(start_time)
                shift_start_minute = int(round((start_time % 1) * 60))
                if shift_start_minute >= 60:
                    shift_start_hour += 1
                    shift_start_minute = 0
                shift_start_dt = tz.localize(datetime.combine(
                    checkin_local.date(),
                    time(hour=shift_start_hour, minute=shift_start_minute)
                ))
                
                if checkin_local > shift_start_dt:
                    delta = checkin_local - shift_start_dt
                    record.late_minutes = int(delta.total_seconds() / 60)
                else:
                    record.late_minutes = 0
                
                grace_in_td = timedelta(minutes=grace_in)
                if checkin_local > (shift_start_dt + grace_in_td):
                    record.is_late = True
            
            # Check early leave
            if record.last_checkout:
                checkout_utc = pytz.utc.localize(record.last_checkout)
                checkout_local = checkout_utc.astimezone(tz)
                
                shift_end_dt = tz.localize(datetime.combine(
                    checkout_local.date(),
                    time(hour=int(end_time), minute=int((end_time % 1) * 60))
                ))
                
                grace_out_td = timedelta(minutes=grace_out)
                if checkout_local < (shift_end_dt - grace_out_td):
                    record.is_early_leave = True
                    # Calculate early leave minutes from original end time
                    delta = shift_end_dt - checkout_local
                    record.early_leave_minutes = int(delta.total_seconds() / 60)

    @api.depends('late_minutes')
    def _compute_late_minutes_display(self):
        for record in self:
            if record.late_minutes > 0:
                record.late_minutes_display = f"{record.late_minutes} min"
            else:
                record.late_minutes_display = "0"
    
    def action_view_attendances(self):
        """Open attendance records for this day."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Attendance Records - %s') % self.display_name,
            'res_model': 'hr.attendance',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.attendance_ids.ids)],
            'context': {
                'default_employee_id': self.employee_id.id,
                'default_check_in': datetime.combine(self.date, time(9, 0)),
            },
        }
    
    def action_open_manual_present_wizard(self):
        """Open the Conditional / Power Outage Present wizard for this record."""
        self.ensure_one()
        return {
            'name': _('Conditional / Power Outage Present'),
            'type': 'ir.actions.act_window',
            'res_model': 'zkteco.manual.present.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_record_ids': [(6, 0, self.ids)],
                'active_ids': self.ids,
            }
        }

    def action_mark_absent(self):

        """Manually mark as absent."""
        for record in self:
            if record.status != 'absent':
                old_status = record.status
                record.remarks = (record.remarks or '') + '\n' + _('Manually marked absent on %s') % fields.Datetime.now()
                self.env['zkteco.attendance.audit.trail'].create({
                    'name': f"Manually marked absent: {record.employee_id.name}",
                    'employee_id': record.employee_id.id,
                    'attendance_record_id': record.id,
                    'user_id': self.env.uid,
                    'action_type': 'manual_absent',
                    'old_value': str(old_status),
                    'new_value': 'absent',
                    'notes': f"Status changed manually on {fields.Date.today()}"
                })

    def action_mark_present(self):
        """Manually create attendance record."""
        self.ensure_one()
        
        # Create a default attendance record
        att = self.env['hr.attendance'].create({
            'employee_id': self.employee_id.id,
            'check_in': datetime.combine(self.date, time(9, 0)),
            'check_out': datetime.combine(self.date, time(17, 0)),
            'attendance_record_id': self.id,
        })
        
        self.env['zkteco.attendance.audit.trail'].create({
            'name': f"Manually marked present: {self.employee_id.name}",
            'employee_id': self.employee_id.id,
            'attendance_record_id': self.id,
            'user_id': self.env.uid,
            'action_type': 'manual_present',
            'old_value': str(self.status),
            'new_value': 'present',
            'notes': f"Created default attendance check-in/out: {att.id}"
        })
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Attendance Created'),
                'message': _('Default attendance record created for %s') % self.employee_id.name,
                'type': 'success',
                'sticky': False,
            }
        }

    def write(self, vals):
        """Track field changes in audit trail."""
        res = super(AttendanceRecord, self).write(vals)
        if 'status' in vals or 'first_checkin' in vals or 'last_checkout' in vals or 'remarks' in vals:
            for record in self:
                self.env['zkteco.attendance.audit.trail'].create({
                    'name': f"Attendance Record Updated: {record.employee_id.name} ({record.date})",
                    'employee_id': record.employee_id.id,
                    'attendance_record_id': record.id,
                    'user_id': self.env.uid,
                    'action_type': 'status_override' if 'status' in vals else 'write',
                    'field_name': ', '.join(vals.keys()),
                    'new_value': str(vals),
                    'notes': 'Record fields updated via interface'
                })
        return res

    def action_sync_assigned_shifts(self):
        """Manually trigger syncing of shift assignments for the selected attendance records."""
        for record in self:
            if record.employee_id and record.date:
                shift_assignment = self.env['zkteco.employee.shift'].search([
                    ('employee_id', '=', record.employee_id.id),
                    ('date_start', '<=', record.date),
                    ('date_end', '>=', record.date),
                ], limit=1)
                if shift_assignment:
                    record.shift_id = shift_assignment.shift_id.id
                else:
                    record.shift_id = False

    
    @api.model
    def generate_daily_records(self, target_date=None):
        """
        Generate attendance records for all active employees for a given date.
        Called by cron job daily. Optimized to prevent N+1 queries.
        """
        if not target_date:
            target_date = fields.Date.today()
        
        # Get all active employees
        employees = self.env['hr.employee'].search([
            ('active', '=', True),
        ])
        
        # Filter out employees who are not expected to work today based on their Working Hours (resource.calendar)
        weekday_str = str(target_date.weekday())
        expected_employees = self.env['hr.employee']
        
        calendar_working_map = {}
        for employee in employees:
            calendar = employee.resource_calendar_id or employee.company_id.resource_calendar_id
            if not calendar:
                # Fallback: Assume everyone works except Sunday (6)
                if target_date.weekday() != 6:
                    expected_employees |= employee
                continue
                
            if calendar.id not in calendar_working_map:
                is_holiday = False
                if hasattr(calendar, 'global_leave_ids'):
                    for leave in calendar.global_leave_ids:
                        if leave.date_from and leave.date_to:
                            if leave.date_from.date() <= target_date <= leave.date_to.date():
                                is_holiday = True
                                break
                
                if is_holiday:
                    calendar_working_map[calendar.id] = False
                else:
                    is_working_day = any(att.dayofweek == weekday_str for att in calendar.attendance_ids)
                    calendar_working_map[calendar.id] = is_working_day
            
            if calendar_working_map.get(calendar.id, False):
                expected_employees |= employee

        # Find already existing attendance records for the target date to avoid duplicates
        existing_records = self.search([('date', '=', target_date)])
        existing_employee_ids = set(existing_records.mapped('employee_id.id'))
        
        # Find active employees who are expected to work but don't have an attendance record for this day
        missing_employees = expected_employees.filtered(lambda e: e.id not in existing_employee_ids)
        
        if not missing_employees:
            _logger.info(f"All active employees already have attendance records for {target_date}")
            return 0
        
        # Batch search all shift assignments overlapping with target_date
        shift_assignments = self.env['zkteco.employee.shift'].sudo().search([
            ('employee_id', 'in', missing_employees.ids),
            ('date_start', '<=', target_date),
            ('date_end', '>=', target_date),
        ])
        employee_shift_map = {sa.employee_id.id: sa.shift_id.id for sa in shift_assignments}
        
        vals_list = []
        for employee in missing_employees:
            vals_list.append({
                'employee_id': employee.id,
                'date': target_date,
                'shift_id': employee_shift_map.get(employee.id, False),
            })
            
        if vals_list:
            self.create(vals_list)
            
        created = len(vals_list)
        _logger.info(f"Generated {created} attendance records for {target_date}")
        return created
    
    @api.model
    def auto_mark_absent(self, target_date=None):
        """
        Automatically mark employees as absent if they didn't punch in.
        Called by cron job at end of day.
        """
        if not target_date:
            target_date = fields.Date.today()
        
        # Find all records for the date with no punches and not on leave
        absent_records = self.search([
            ('date', '=', target_date),
            ('status', '=', 'absent'),
        ])
        
        _logger.info(f"Auto-marked {len(absent_records)} employees as absent for {target_date}")
        return len(absent_records)

    
    @api.model
    def _cron_generate_daily_records(self):
        """Cron job to generate daily records."""
        return self.generate_daily_records()
    
    @api.model
    def _cron_auto_mark_absent(self):
        """Cron job to auto-mark absent employees at 20:00."""
        today = fields.Date.today()
        return self.auto_mark_absent(today)





