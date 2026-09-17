# -*- coding: utf-8 -*-
from datetime import timedelta
from odoo import api, fields, models, _
import logging

_logger = logging.getLogger(__name__)


class HrLeave(models.Model):
    _inherit = 'hr.leave'

    def _sync_with_zkteco_attendance_records(self):
        """
        Synchronize leave dates and statuses with zkteco.attendance.record
        so that employees on leave are accurately displayed as 'On Leave'
        with their leave type rather than 'Absent'.
        """
        AttendanceRecord = self.env['zkteco.attendance.record'].sudo()

        for leave in self:
            if not leave.employee_id:
                continue

            # Determine start and end dates
            date_from = leave.request_date_from or (leave.date_from.date() if leave.date_from else False)
            date_to = leave.request_date_to or (leave.date_to.date() if leave.date_to else False)

            if not date_from:
                continue
            if not date_to:
                date_to = date_from

            # Iterate through each day in the leave span
            curr_date = date_from
            while curr_date <= date_to:
                # Find or create daily attendance record
                record = AttendanceRecord.search([
                    ('employee_id', '=', leave.employee_id.id),
                    ('date', '=', curr_date)
                ], limit=1)

                if not record and leave.state in ('confirm', 'validate1', 'validate'):
                    # Create the record for this day so it displays On Leave
                    record = AttendanceRecord.create({
                        'employee_id': leave.employee_id.id,
                        'date': curr_date,
                    })

                if record:
                    # Force recompute of leave info, status, display, and expected hours
                    record._compute_leave_info()
                    record._compute_status()
                    record._compute_status_display()
                    record._compute_worked_hours()
                    record._compute_expected_hours()
                    record._compute_overtime_hours()

                curr_date += timedelta(days=1)

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._sync_with_zkteco_attendance_records()
        return records

    def write(self, vals):
        res = super().write(vals)
        trigger_fields = {'state', 'request_date_from', 'request_date_to', 'date_from', 'date_to', 'employee_id', 'holiday_status_id', 'active'}
        if any(f in vals for f in trigger_fields):
            self._sync_with_zkteco_attendance_records()
        return res

    def action_validate(self, *args, **kwargs):
        res = super().action_validate(*args, **kwargs)
        self._sync_with_zkteco_attendance_records()
        return res

    def action_approve(self, *args, **kwargs):
        res = super().action_approve(*args, **kwargs)
        self._sync_with_zkteco_attendance_records()
        return res

    def action_refuse(self, *args, **kwargs):
        res = super().action_refuse(*args, **kwargs)
        self._sync_with_zkteco_attendance_records()
        return res

    def action_cancel(self, *args, **kwargs):
        res = super().action_cancel(*args, **kwargs)
        self._sync_with_zkteco_attendance_records()
        return res

    def unlink(self):
        leaves_to_sync = self.filtered(lambda l: l.employee_id)
        # Store metadata before deletion to update records
        dates_and_employees = []
        for leave in leaves_to_sync:
            d_from = leave.request_date_from or (leave.date_from.date() if leave.date_from else False)
            d_to = leave.request_date_to or (leave.date_to.date() if leave.date_to else False)
            if d_from and d_to:
                dates_and_employees.append((leave.employee_id.id, d_from, d_to))

        res = super().unlink()

        AttendanceRecord = self.env['zkteco.attendance.record'].sudo()
        for emp_id, d_from, d_to in dates_and_employees:
            curr = d_from
            while curr <= d_to:
                recs = AttendanceRecord.search([
                    ('employee_id', '=', emp_id),
                    ('date', '=', curr)
                ])
                if recs:
                    recs._compute_leave_info()
                    recs._compute_status()
                    recs._compute_status_display()
                    recs._compute_worked_hours()
                    recs._compute_expected_hours()
                curr += timedelta(days=1)

        return res
