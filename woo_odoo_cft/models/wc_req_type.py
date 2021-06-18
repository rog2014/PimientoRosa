from odoo import fields, models


class wc_req_type(models.Model):
    _name = 'wc.req.type'

    name = fields.Char('Type')
