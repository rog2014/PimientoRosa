from odoo import models, fields


class WcProductAttribute(models.Model):
    _name = "wc.product.attribute.cft"
    _description = "WooCommerce Product Attribute"

    name = fields.Char('Name', required=1, translate=True)
    slug = fields.Char(string='Slug', help="An alphanumeric identifier for the resource unique to its type.")
    order_by = fields.Selection(
        [('menu_order', 'Custom Ordering'), ('name', 'Name'), ('name_num', 'Name(numeric)'), ('id', 'Term ID')],
        default="menu_order", string='Default sort order')
    wc_attribute_id = fields.Char("WooCommerce Attribute Id")
    avail_in_wc = fields.Boolean("Available in WooCommerce", default=False)
    attribute_id = fields.Many2one('product.attribute', 'Attribute', required=1, copy=False)
    wc_instance_id = fields.Many2one("wc.instance.cft", "Instance", required=True, ondelete='cascade')
    attribute_type = fields.Selection([('select', 'Select'), ('text', 'Text')], string='Attribute Type',
                                      default='select')
    has_archives = fields.Boolean(string="Enable Archives?", help="Enable/Disable attribute archives")


class WcProductAttributeTerm(models.Model):
    _name = "wc.product.attribute.cft.term"
    _description = "WooCommerce Product Attribute Term"

    name = fields.Char('Name', required=1, translate=True)
    description = fields.Char('Description')
    slug = fields.Char(string='Slug', help="An alphanumeric identifier for the resource unique to its type.")
    count = fields.Integer("Count")
    wc_attribute_term_id = fields.Char("WooCommerce Attribute Term Id")
    wc_attribute_id = fields.Char("WooCommerce Attribute Id")
    avail_in_wc = fields.Boolean("Available in WooCommerce", default=False)
    attribute_id = fields.Many2one('product.attribute', 'Attribute', required=1, copy=False)
    attribute_value_id = fields.Many2one('product.attribute.value', 'Attribute Value', required=1, copy=False)
    wc_instance_id = fields.Many2one("wc.instance.cft", "Instance", required=True, ondelete='cascade')
