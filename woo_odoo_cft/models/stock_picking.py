from odoo import models, fields, api, _


class StockPicking(models.Model):
    _inherit = "stock.picking"

    @api.depends("group_id")
    def get_wc_orders(self):
        sale_obj = self.env['sale.order']
        for record in self:
            if record.group_id:
                order = sale_obj.search([('procurement_group_id', '=', record.group_id.id)])
                if order.wc_order_id:
                    record.is_wc_delivery_order = True
                    record.wc_instance_id = order.wc_instance_id.id
                else:
                    record.is_wc_delivery_order = False
                    record.wc_instance_id = False

    updated_in_wc = fields.Boolean("Updated In WooCommerce", default=False)
    is_wc_delivery_order = fields.Boolean("WooCommerce Delivery Order", compute="get_wc_orders", store=True)
    wc_instance_id = fields.Many2one("wc.instance.cft", "WooCommerce Instance", store=True, compute="get_wc_orders")


class delivery_carrier(models.Model):
    _inherit = "delivery.carrier"

    wc_code = fields.Char("WooCommerce Code", help="WooCommerce Delivery Code")
