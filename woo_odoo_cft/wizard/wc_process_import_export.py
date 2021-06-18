from odoo import models, fields, api
from odoo.exceptions import Warning
from _collections import OrderedDict


class WcImportExportProcess(models.TransientModel):
    _name = 'wc.import.export.process.cft'
    _description = "WooCommerce Import Export Process"

    def _get_wc_op_vals(self):
        vals = [('export', 'Export'), ('update', 'Update')]
        if 'process_type' in self._context and self._context.get('process_type') == 'export_wc_products':
            vals.append(('update_price', 'Update Price'))
            vals.append(('update_image', 'Update Image'))
            vals.append(('update_stock', 'Update Stock'))
        return vals

    wc_instance_ids = fields.Many2many("wc.instance.cft", string="Instances")
    update_price_in_product = fields.Boolean("Set Price", default=False)
    update_stock_in_product = fields.Boolean("Set Stock", default=False)
    publish = fields.Boolean("Publish In Website", default=False)
    update_image_in_product_export = fields.Boolean("Set Image", default=False)
    update_image_in_product_update = fields.Boolean("Set Image", default=False)
    is_update_stock = fields.Boolean("Update Stock", help="Update Stock Level from Odoo to WooCommerce.")
    is_update_price = fields.Boolean("Update Price", help="Update price of products from Odoo to WooCommerce.")
    is_update_image = fields.Boolean("Update Images", help="Update product images from Odoo to WooCommerce.")
    sync_images = fields.Boolean("Sync Images?", default=False)
    export_image = fields.Boolean("Export Image?", default=False)
    sync_price_with_product = fields.Boolean("Sync Product Price?",
                                             help="Check if you want to import price along with products",
                                             default=False)
    wc_coupon_ids = fields.Many2many('wc.coupons.cft', string="Coupons")
    wc_categ_ids = fields.Many2many('wc.category.cft', string="Category")
    wc_tag_ids = fields.Many2many('wc.tags.cft', string="Tags")
    wc_products_ids = fields.Many2many('wc.product.template.cft', string="Products")
    wc_op = fields.Selection(_get_wc_op_vals, "Export/Update Operation")

    @api.model
    def default_get(self, fields):
        res = super(WcImportExportProcess, self).default_get(fields)
        if 'default_instance_id' in self._context:
            res.update({'wc_instance_ids': [(6, 0, [self._context.get('default_instance_id')])]})
        elif 'wc_instance_ids' in fields:
            instances = self.env['wc.instance.cft'].search([('state', '=', 'confirm')])
            res.update({'wc_instance_ids': [(6, 0, instances.ids)]})
        return res

    def publish_wc_products(self):
        wc_tmpl_obj = self.env['wc.product.template.cft']
        for wc_instance in self.wc_instance_ids:
            instance_context = dict(self.env.context)
            instance_context.update({'lang': wc_instance.lang_id.code})
            wc_tmpl_obj = wc_tmpl_obj.with_context(instance_context)
            if self.wc_products_ids:
                wc_products = wc_tmpl_obj.search(
                    [('wc_instance_id', '=', wc_instance.id), ('id', 'in', self.wc_products_ids.ids),
                     ('avail_in_wc', '=', True)])
            else:
                wc_products = wc_tmpl_obj.search(
                    [('wc_instance_id', '=', wc_instance.id), ('avail_in_wc', '=', True)])
            for wc_product in wc_products:
                wc_product.wc_published()
        return True

    def unpublish_wc_products(self):
        wc_tmpl_obj = self.env['wc.product.template.cft']
        for wc_instance in self.wc_instance_ids:
            instance_context = dict(self.env.context)
            instance_context.update({'lang': wc_instance.lang_id.code})
            wc_tmpl_obj = wc_tmpl_obj.with_context(instance_context)
            if self.wc_products_ids:
                wc_products = wc_tmpl_obj.search(
                    [('wc_instance_id', '=', wc_instance.id), ('id', 'in', self.wc_products_ids.ids),
                     ('avail_in_wc', '=', True)])
            else:
                wc_products = wc_tmpl_obj.search(
                    [('wc_instance_id', '=', wc_instance.id), ('avail_in_wc', '=', True)])
            for wc_product in wc_products:
                wc_product.wc_unpublished()
        return True

    def export_wc_coupons(self):
        wc_coupons_obj = self.env['wc.coupons.cft']
        for wc_instance in self.wc_instance_ids:
            instance_context = dict(self.env.context)
            instance_context.update({'lang': wc_instance.lang_id.code})
            wc_coupons_obj = wc_coupons_obj.with_context(instance_context)
            if self.wc_coupon_ids:
                wc_coupons = wc_coupons_obj.search(
                    [('wc_instance_id', '=', wc_instance.id), ('id', 'in', self.wc_coupon_ids.ids),
                     ('avail_in_wc', '=', False)])
            else:
                wc_coupons = wc_coupons_obj.search(
                    [('wc_instance_id', '=', wc_instance.id), ('avail_in_wc', '=', False)])

            if wc_coupons:
                wc_coupons_obj.export_update_coupons(wc_instance, wc_coupons, op_type="export")
        return True

    def update_wc_categs(self):
        wc_categ_obj = self.env['wc.category.cft']
        for wc_instance in self.wc_instance_ids:
            instance_context = dict(self.env.context)
            instance_context.update({'lang': wc_instance.lang_id.code})
            wc_categ_obj = wc_categ_obj.with_context(instance_context)
            if self.wc_categ_ids:
                wc_categs = wc_categ_obj.search(
                    [('wc_instance_id', '=', wc_instance.id), ('id', 'in', self.wc_categ_ids.ids),
                     ('avail_in_wc', '=', True)])
            else:
                wc_categs = wc_categ_obj.search(
                    [('wc_instance_id', '=', wc_instance.id), ('avail_in_wc', '=', True)])

            if wc_categs:
                wc_categ_obj.update_product_categs(wc_instance, wc_categs, export_image=self.export_image)
        return True

    def export_wc_categs(self):
        wc_categ_obj = self.env['wc.category.cft']
        for wc_instance in self.wc_instance_ids:
            instance_context = dict(self.env.context)
            instance_context.update({'lang': wc_instance.lang_id.code})
            wc_categ_obj = wc_categ_obj.with_context(instance_context)
            if self.wc_categ_ids:
                wc_categs = wc_categ_obj.search(
                    [('wc_instance_id', '=', wc_instance.id), ('id', 'in', self.wc_categ_ids.ids),
                     ('avail_in_wc', '=', False)])
            else:
                wc_categs = wc_categ_obj.search(
                    [('wc_instance_id', '=', wc_instance.id), ('avail_in_wc', '=', False)])
            if wc_categs:
                wc_categ_obj.export_wc_product_category(wc_instance, wc_categs)
        return True

    def update_wc_tags(self):
        wc_tags_obj = self.env['wc.tags.cft']
        for wc_instance in self.wc_instance_ids:
            instance_context = dict(self.env.context)
            instance_context.update({'lang': wc_instance.lang_id.code})
            wc_tags_obj = wc_tags_obj.with_context(instance_context)
            if self.wc_tag_ids:
                wc_tags = wc_tags_obj.search(
                    [('wc_instance_id', '=', wc_instance.id), ('id', 'in', self.wc_tag_ids.ids),
                     ('avail_in_wc', '=', True)])
            else:
                wc_tags = wc_tags_obj.search(
                    [('wc_instance_id', '=', wc_instance.id), ('avail_in_wc', '=', True)])
            if wc_tags:
                wc_tags_obj.update_product_tags(wc_instance, wc_tags)
        return True

    def export_wc_tags(self):
        wc_tags_obj = self.env['wc.tags.cft']
        for wc_instance in self.wc_instance_ids:
            instance_context = dict(self.env.context)
            instance_context.update({'lang': wc_instance.lang_id.code})
            wc_tags_obj = wc_tags_obj.with_context(instance_context)
            if self.wc_tag_ids:
                wc_tags = wc_tags_obj.search(
                    [('wc_instance_id', '=', wc_instance.id), ('id', 'in', self.wc_tag_ids.ids),
                     ('avail_in_wc', '=', False)])
            else:
                wc_tags = wc_tags_obj.search(
                    [('wc_instance_id', '=', wc_instance.id), ('avail_in_wc', '=', False)])

            if wc_tags:
                wc_tags_obj.export_product_tags(wc_instance, wc_tags, export_image=self.export_image)
        return True

    def export_wc_products(self):
        wc_tmpl_obj = self.env['wc.product.template.cft']
        for wc_instance in self.wc_instance_ids:
            instance_context = dict(self.env.context)
            instance_context.update({'lang': wc_instance.lang_id.code})
            wc_tmpl_obj = wc_tmpl_obj.with_context(instance_context)
            if self.wc_products_ids:
                wc_products = wc_tmpl_obj.search(
                    [('wc_instance_id', '=', wc_instance.id), ('id', 'in', self.wc_products_ids.ids),
                     ('avail_in_wc', '=', False)])
            else:
                wc_products = wc_tmpl_obj.search(
                    [('wc_instance_id', '=', wc_instance.id), ('avail_in_wc', '=', False)])
            wc_products and wc_tmpl_obj.export_wc_products(wc_instance, wc_products,
                                                           update_price=self.is_update_price,
                                                           update_stock=self.is_update_stock,
                                                           publish=self.publish,
                                                           update_image=self.is_update_image)
        return True

    def update_wc_products(self):
        wc_tmpl_obj = self.env['wc.product.template.cft']
        for wc_instance in self.wc_instance_ids:
            instance_context = dict(self.env.context)
            instance_context.update({'lang': wc_instance.lang_id.code})
            wc_tmpl_obj = wc_tmpl_obj.with_context(instance_context)
            if self.wc_products_ids:
                wc_products = wc_tmpl_obj.search(
                    [('wc_instance_id', '=', wc_instance.id), ('id', 'in', self.wc_products_ids.ids),
                     ('avail_in_wc', '=', True)])
            else:
                wc_products = wc_tmpl_obj.search(
                    [('wc_instance_id', '=', wc_instance.id), ('avail_in_wc', '=', True)])
            wc_products and wc_tmpl_obj.update_products(wc_instance, wc_products, update_image=self.is_update_image)
        return True

    def import_wc_product_stock(self):
        wc_tmpl_obj = self.env['wc.product.template.cft']
        for wc_instance in self.wc_instance_ids:
            instance_context = dict(self.env.context)
            instance_context.update({'lang': wc_instance.lang_id.code})
            wc_tmpl_obj = wc_tmpl_obj.with_context(instance_context)
            if self.wc_products_ids:
                wc_products = wc_tmpl_obj.search(
                    [('wc_instance_id', '=', wc_instance.id), ('id', 'in', self.wc_products_ids.ids),
                     ('avail_in_wc', '=', True)])
            else:
                wc_products = wc_tmpl_obj.search(
                    [('wc_instance_id', '=', wc_instance.id), ('avail_in_wc', '=', True)])
            wc_products and wc_tmpl_obj.import_wc_stock(wc_instance, wc_products)
        return True

    def update_wc_product_price(self):
        wc_tmpl_obj = self.env['wc.product.template.cft']
        for wc_instance in self.wc_instance_ids:
            instance_context = dict(self.env.context)
            instance_context.update({'lang': wc_instance.lang_id.code})
            wc_tmpl_obj = wc_tmpl_obj.with_context(instance_context)
            if self.wc_products_ids:
                wc_products = wc_tmpl_obj.search(
                    [('wc_instance_id', '=', wc_instance.id), ('id', 'in', self.wc_products_ids.ids),
                     ('avail_in_wc', '=', True)])
            else:
                wc_products = wc_tmpl_obj.search(
                    [('wc_instance_id', '=', wc_instance.id), ('avail_in_wc', '=', True)])
            wc_products and wc_tmpl_obj.update_wc_product_price(wc_instance, wc_products)
        return True

    def update_wc_product_image(self):
        wc_tmpl_obj = self.env['wc.product.template.cft']
        for wc_instance in self.wc_instance_ids:
            instance_context = dict(self.env.context)
            instance_context.update({'lang': wc_instance.lang_id.code})
            wc_tmpl_obj = wc_tmpl_obj.with_context(instance_context)
            if self.wc_products_ids:
                wc_products = wc_tmpl_obj.search(
                    [('wc_instance_id', '=', wc_instance.id), ('id', 'in', self.wc_products_ids.ids),
                     ('avail_in_wc', '=', True)])
            else:
                wc_products = wc_tmpl_obj.search(
                    [('wc_instance_id', '=', wc_instance.id), ('avail_in_wc', '=', True)])
            wc_products and wc_tmpl_obj.update_wc_product_image(wc_instance, wc_products)
        return True

    def update_wc_product_stock(self):
        wc_tmpl_obj = self.env['wc.product.template.cft']
        for wc_instance in self.wc_instance_ids:
            instance_context = dict(self.env.context)
            instance_context.update({'lang': wc_instance.lang_id.code})
            wc_tmpl_obj = wc_tmpl_obj.with_context(instance_context)
            if self.wc_products_ids:
                wc_products = wc_tmpl_obj.search(
                    [('wc_instance_id', '=', wc_instance.id), ('id', 'in', self.wc_products_ids.ids),
                     ('avail_in_wc', '=', True)])
            else:
                wc_products = wc_tmpl_obj.search(
                    [('wc_instance_id', '=', wc_instance.id), ('avail_in_wc', '=', True)])
            wc_products and wc_tmpl_obj.update_wc_product_stock(wc_instance, wc_products)
        return True

    def update_wc_coupons(self):
        wc_coupons_obj = self.env['wc.coupons.cft']
        for wc_instance in self.wc_instance_ids:
            instance_context = dict(self.env.context)
            instance_context.update({'lang': wc_instance.lang_id.code})
            wc_coupons_obj = wc_coupons_obj.with_context(instance_context)
            if self.wc_coupon_ids:
                wc_coupons = wc_coupons_obj.search(
                    [('wc_instance_id', '=', wc_instance.id), ('id', 'in', self.wc_coupon_ids.ids),
                     ('avail_in_wc', '=', True)])
            else:
                wc_coupons = wc_coupons_obj.search(
                    [('wc_instance_id', '=', wc_instance.id), ('avail_in_wc', '=', True)])

            if wc_coupons:
                wc_coupons_obj.export_update_coupons(wc_instance, wc_coupons, op_type="update")
        return True

    def import_wc_coupons(self):
        for instance in self.wc_instance_ids:
            instance_context = dict(self.env.context)
            instance_context.update({'lang': instance.lang_id.code})
            self = self.with_context(instance_context)
            self.env['wc.coupons.cft'].import_coupons(instance)
        return True

    def import_wc_sale_orders(self):
        for instance in self.wc_instance_ids:
            instance_context = dict(self.env.context)
            instance_context.update({'lang': instance.lang_id.code})
            self = self.with_context(instance_context)
            self.env['sale.order'].import_wc_orders(instance)
        return True

    def import_wc_categs(self):
        for instance in self.wc_instance_ids:
            instance_context = dict(self.env.context)
            instance_context.update({'lang': instance.lang_id.code})
            self = self.with_context(instance_context)
            self.env['wc.category.cft'].sync_product_category(instance, self.sync_images)
        return True

    def import_wc_tags(self):
        for instance in self.wc_instance_ids:
            instance_context = dict(self.env.context)
            instance_context.update({'lang': instance.lang_id.code})
            self = self.with_context(instance_context)
            self.env['wc.tags.cft'].sync_product_tags(instance)
        return True

    def import_wc_customers(self):
        for instance in self.wc_instance_ids:
            instance_context = dict(self.env.context)
            instance_context.update({'lang': instance.lang_id.code})
            self = self.with_context(instance_context)
            self.env['res.partner'].import_wc_customers(instance)
        return True

    def import_wc_products(self):
        for instance in self.wc_instance_ids:
            instance_context = dict(self.env.context)
            instance_context.update({'lang': instance.lang_id.code})
            self = self.with_context(instance_context)
            wc_products = []
            if self.wc_products_ids:
                wc_products = self.env['wc.product.template.cft'].search(
                    [('id', 'in', self.wc_products_ids.ids), ('wc_instance_id', '=', instance.id),
                     ('avail_in_wc', '=', True)])
                if not wc_products:
                    continue
            self.env['wc.product.template.cft'].import_wc_products(instance, wc_tmpl_ids=wc_products,
                                                                   update_price=self.sync_price_with_product,
                                                                   sync_images_with_product=self.sync_images,
                                                                   update_template=True)
        return True

    def update_wc_order_status(self):
        for instance in self.wc_instance_ids:
            instance_context = dict(self.env.context)
            instance_context.update({'lang': instance.lang_id.code})
            self = self.with_context(instance_context)
            self.env['sale.order'].update_wc_order_status(instance)
        return True

    def prepare_wc_product(self):
        wc_template_obj = self.env['wc.product.template.cft']
        wc_product_obj = self.env['wc.product.product.cft']
        wc_product_categ = self.env['wc.category.cft']
        wc_product_image_obj = self.env['wc.product.image.cft']
        template_ids = self._context.get('active_ids', [])
        odoo_templates = self.env['product.template'].search(
            [('id', 'in', template_ids), ('default_code', '!=', False)])
        if not odoo_templates:
            raise Warning("Internal Reference (SKU) not set in selected products")
        for wc_instance in self.wc_instance_ids:
            instance_context = dict(self.env.context)
            instance_context.update({'lang': wc_instance.lang_id.code})
            self = self.with_context(instance_context)
            wc_template_obj = wc_template_obj.with_context(instance_context)
            wc_product_obj = wc_product_obj.with_context(instance_context)
            wc_product_categ = wc_product_categ.with_context(instance_context)
            wc_product_image_obj = wc_product_image_obj.with_context(instance_context)
            for odoo_template in odoo_templates:
                odoo_template = odoo_template.with_context(instance_context)
                wc_categ_ids = [(6, 0, [])]
                wc_template = wc_template_obj.search(
                    [('wc_instance_id', '=', wc_instance.id), ('product_tmpl_id', '=', odoo_template.id)])
                if wc_template:
                    continue
                odoo_categ = odoo_template.categ_id or ''
                if odoo_categ.id:
                    self.create_categ_in_wc(odoo_categ, wc_instance)
                    wc_categ_id = wc_product_categ.search([('name', '=', odoo_categ.name)])
                    if not wc_categ_id:
                        wc_categ_id = wc_product_categ.create(
                            {'name': odoo_categ.name, 'wc_instance_id': wc_instance.id})
                    else:
                        wc_categ_id.write({'name': odoo_categ.name})
                    wc_categ_ids = [(6, 0, wc_categ_id.ids)]
                wc_template = wc_template_obj.create(
                    {'wc_instance_id': wc_instance.id, 'product_tmpl_id': odoo_template.id,
                     'name': odoo_template.name, 'wc_categ_ids': wc_categ_ids,
                     'description': odoo_template.description_sale, 'short_description': odoo_template.description})
                if odoo_template.image_1920:
                    wc_product_image_obj.create(
                        {'sequence': 0, 'wc_instance_id': wc_instance.id, 'image': odoo_template.image_1920,
                         'wc_product_tmpl_id': wc_template.id})
                for variant in odoo_template.product_variant_ids:
                    wc_variant = wc_product_obj.search(
                        [('wc_instance_id', '=', wc_instance.id), ('product_id', '=', variant.id)])
                    if not wc_variant:
                        wc_variant.create({'wc_instance_id': wc_instance.id, 'product_id': variant.id,
                                           'wc_template_id': wc_template.id, 'default_code': variant.default_code,
                                           'name': variant.display_name})
        return True

    def create_categ_in_wc(self, categ_id, wc_instance, ctg_list=[]):
        wc_product_categ = self.env['wc.category.cft']
        if categ_id:
            ctg_list.append(categ_id)
            self.create_categ_in_wc(categ_id.parent_id, wc_instance, ctg_list=ctg_list)
        else:
            for categ_id in list(OrderedDict.fromkeys(reversed(ctg_list))):
                wc_product_parent_categ = categ_id.parent_id and wc_product_categ.search(
                    [('name', '=', categ_id.parent_id.name), ('wc_instance_id', '=', wc_instance.id)], limit=1) or False
                if wc_product_parent_categ:
                    wc_product_category = wc_product_categ.search(
                        [('name', '=', categ_id.name), ('parent_id', '=', wc_product_parent_categ.id),
                         ('wc_instance_id', '=', wc_instance.id)], limit=1)
                else:
                    wc_product_category = wc_product_categ.search(
                        [('name', '=', categ_id.name), ('wc_instance_id', '=', wc_instance.id)], limit=1)
                if not wc_product_category:
                    if not categ_id.parent_id:
                        parent_id = wc_product_categ.create({'name': categ_id.name, 'wc_instance_id': wc_instance.id})
                    else:
                        parent_id = wc_product_categ.search(
                            [('name', '=', categ_id.parent_id.name), ('wc_instance_id', '=', wc_instance.id)], limit=1)
                        wc_product_categ.create(
                            {'name': categ_id.name, 'wc_instance_id': wc_instance.id, 'parent_id': parent_id.id})
                elif not wc_product_category.parent_id and categ_id.parent_id:
                    parent_id = wc_product_categ.search(
                        [('name', '=', categ_id.parent_id.name), ('parent_id', '=', wc_product_parent_categ.id),
                         ('wc_instance_id', '=', wc_instance.id)])
                    if not parent_id:
                        wc_product_categ.create({'name': categ_id.name, 'wc_instance_id': wc_instance.id})
                    if not parent_id.parent_id.id == wc_product_category.id and wc_product_categ.instance_id.id == wc_instance.id:
                        wc_product_category.write({'parent_id': parent_id.id})
        return True

    def check_products(self, wc_templates):
        if self.env['wc.product.product.cft'].search(
                [('wc_template_id', 'in', wc_templates.ids), ('default_code', '=', False)]):
            raise Warning("Default code is not set in some variants")

    def filter_templates(self, wc_templates):
        filter_templates = []
        for wc_template in wc_templates:
            if not self.env['wc.product.product.cft'].search(
                    [('wc_template_id', '=', wc_template.id), ('default_code', '=', False)]):
                filter_templates.append(wc_template)
        return filter_templates
