from odoo import fields, models


class StockInventory(models.Model):
    _inherit = 'stock.inventory'

    wc_instance_id = fields.Many2one("wc.instance.cft", "WooCommerce Instance")
