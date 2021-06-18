from odoo import models, fields, api


class ProductProduct(models.Model):
    _inherit = 'product.product'

    def _wc_product_count(self):
        wc_product_obj = self.env['wc.product.product.cft']
        for product in self:
            wc_products = wc_product_obj.search([('product_id', '=', product.id)])
            product.wc_product_count = len(wc_products) if wc_products else 0

    wc_product_count = fields.Integer(string='# Sales', compute='_wc_product_count')

class ProductTemplate(models.Model):
    _inherit = 'product.template'

    def _wc_template_count(self):
        wc_product_template_obj = self.env['wc.product.template.cft']
        for template in self:
            wc_templates = wc_product_template_obj.search([('product_tmpl_id', '=', template.id)])
            template.wc_template_count = len(wc_templates) if wc_templates else 0

    wc_template_count = fields.Integer(string='# Sales', compute='_wc_template_count')
