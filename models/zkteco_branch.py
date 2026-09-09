from odoo import models, fields

class ZKTecoBranch(models.Model):
    _name = 'zkteco.branch'
    _description = 'ZKTeco Branch'
    _order = 'name'

    name = fields.Char(string='Branch Name', required=True)
    code = fields.Char(string='Branch Code')
    active = fields.Boolean(string='Active', default=True)

    device_ids = fields.One2many('zkteco.device', 'branch_id', string='Devices')
    employee_ids = fields.One2many('hr.employee', 'branch_id', string='Employees')
