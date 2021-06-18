from odoo import models, fields, api


class WcProductImage(models.Model):
    _name = 'wc.product.image.cft'
    _rec_name = "sequence"
    _order = 'sequence'
    _description = "WooCommerce Gallery Image"

    @api.depends('wc_product_tmpl_id')
    def _set_instance(self):
        for wc_gallery_img in self:
            wc_gallery_img.wc_instance_id = wc_gallery_img.wc_product_tmpl_id.wc_instance_id.id

    sequence = fields.Integer("Sequence")
    wc_instance_id = fields.Many2one("wc.instance.cft", "Instance", readonly=True, compute="_set_instance", store=True,
                                     ondelete='cascade')
    image = fields.Binary("Image", required=True)
    wc_product_tmpl_id = fields.Many2one('wc.product.template.cft', string='WooCommerce Product')
    url = fields.Char(size=600, string='Image URL')
    response_url = fields.Char(size=600, string='Response URL', help="URL from WooCommerce")
    wc_image_id = fields.Integer("Image Id", help="WooCommerce Image Id")
