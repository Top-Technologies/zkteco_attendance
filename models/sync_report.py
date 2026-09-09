from odoo import models, fields, api, tools

class ZKTecoSyncReport(models.Model):
    _name = 'zkteco.sync.report'
    _description = 'ZKTeco Sync Report'
    _auto = False
    _order = 'sync_rate asc, device_id'

    device_id = fields.Many2one('zkteco.device', string='Device', readonly=True)
    device_name = fields.Char(string='Device Name', readonly=True)
    branch_id = fields.Many2one('zkteco.branch', string='Branch', readonly=True)
    is_online = fields.Boolean(string='Is Online', readonly=True)
    last_sync = fields.Datetime(string='Last Sync', readonly=True)

    raw_logs_count = fields.Integer(string='Raw Logs', readonly=True)
    processed_records_count = fields.Integer(string='Processed Records', readonly=True)
    sync_rate = fields.Float(string='Sync Rate (%)', readonly=True)
    error_count = fields.Integer(string='Error Logs', readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, 'zkteco_sync_report')
        self.env.cr.execute(f"""
            CREATE OR REPLACE VIEW zkteco_sync_report AS (
                SELECT
                    d.id as id,
                    d.id as device_id,
                    d.name as device_name,
                    d.branch_id as branch_id,
                    CASE

                        WHEN d.ip_address = 'cloud' OR (d.last_sync IS NOT NULL AND d.last_sync >= (NOW() AT TIME ZONE 'UTC' - INTERVAL '60 seconds')) THEN TRUE
                        ELSE FALSE
                    END as is_online,
                    d.last_sync as last_sync,

                    (SELECT count(*) FROM zkteco_attendance WHERE device_id = d.id) as raw_logs_count,
                    (SELECT count(*) FROM zkteco_attendance WHERE device_id = d.id AND state = 'processed') as processed_records_count,
                    (SELECT count(*) FROM zkteco_attendance WHERE device_id = d.id AND state = 'error') as error_count,
                    CASE
                        WHEN (SELECT count(*) FROM zkteco_attendance WHERE device_id = d.id) = 0 THEN 0
                        ELSE ((SELECT count(*) FROM zkteco_attendance WHERE device_id = d.id AND state = 'processed')::float /
                              (SELECT count(*) FROM zkteco_attendance WHERE device_id = d.id)::float) * 100
                    END as sync_rate
                FROM
                    zkteco_device d
            )
        """)

