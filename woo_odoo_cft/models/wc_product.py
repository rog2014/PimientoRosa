from odoo import models, fields, api
from datetime import datetime
from ..wc_api import img_file_upload
import base64
import requests
import hashlib


class WcProductTemplate(models.Model):
    _name = "wc.product.template.cft"
    _order = 'product_tmpl_id'
    _description = "WooCommerce Product Template"

    @api.depends('wc_product_ids.avail_in_wc', 'wc_product_ids.variant_id')
    def get_total_sync_variants(self):
        wc_product_obj = self.env['wc.product.product.cft']
        for template in self:
            variants = wc_product_obj.search(
                [('id', 'in', template.wc_product_ids.ids), ('avail_in_wc', '=', True),
                 ('variant_id', '!=', False)])
            template.total_sync_variants = len(variants.ids)

    @api.depends('wc_product_ids.variant_id')
    def get_total_variants(self):
        wc_product_obj = self.env['wc.product.product.cft']
        for template in self:
            variants = wc_product_obj.search([('id', 'in', template.wc_product_ids.ids)])
            template.total_variants = len(variants.ids)

    name = fields.Char("Name", translate=True)
    wc_instance_id = fields.Many2one("wc.instance.cft", "Instance", required=True, ondelete='cascade')
    product_tmpl_id = fields.Many2one("product.template", "Product Template", required=1)
    wc_categ_ids = fields.Many2many('wc.category.cft', 'wc_template_categ_rel', 'wc_template_id', 'wc_categ_id',
                                    "Categories")
    wc_tag_ids = fields.Many2many('wc.tags.cft', 'wc_template_tags_rel', 'wc_template_id', 'wc_tag_id', "Tags")
    wc_tmpl_id = fields.Char("WooCommerce Template Id")
    avail_in_wc = fields.Boolean("Available in WooCommerce")
    wc_product_ids = fields.One2many("wc.product.product.cft", "wc_template_id", "Products")
    wc_gallery_image_ids = fields.One2many("wc.product.image.cft", "wc_product_tmpl_id", "Images")
    created_at = fields.Datetime("Created At")
    updated_at = fields.Datetime("Updated At")
    taxable = fields.Boolean("Taxable", default=True)
    website_published = fields.Boolean('Available in the website', copy=False)
    description = fields.Html("Description", translate=True)
    short_description = fields.Html("Short Description", translate=True)
    total_variants = fields.Integer("Total Variants", compute=get_total_variants, store=True)
    total_sync_variants = fields.Integer("Total Sync Variants", compute="get_total_sync_variants", store=True)

    @api.onchange("product_tmpl_id")
    def on_change_product(self):
        for record in self:
            record.name = record.product_tmpl_id.name

    def wc_unpublished(self):
        wc_instance = self.wc_instance_id
        wc_job = self.env['wc.process.job.cft'].create(
            {'wc_instance_id': wc_instance.id, 'process_type': 'product', 'operation_type': 'update',
             'message': 'Process for UnPublish Products'})
        wcapi = wc_instance.wc_connect()
        if self.wc_tmpl_id:
            info = {'status': 'draft'}
            info.update({'id': self.wc_tmpl_id})
            res = wcapi.post('products/batch', {'update': [info]}, wc_job=wc_job)
            if res:
                self.write({'website_published': False})
        return True

    def wc_published(self):
        wc_instance = self.wc_instance_id
        wc_job = self.env['wc.process.job.cft'].create(
            {'wc_instance_id': wc_instance.id, 'process_type': 'product', 'operation_type': 'update',
             'message': 'Process for Publish Products'})
        wcapi = wc_instance.wc_connect()
        if self.wc_tmpl_id:
            info = {'status': 'publish'}
            info.update({'id': self.wc_tmpl_id})
            res = wcapi.post('products/batch', {'update': [info]}, wc_job=wc_job)
            if res:
                self.write({'website_published': True})
        return True

    def sync_wc_product_categ(self, wcapi, wc_instance, wc_categories, sync_images_with_product=False,
                              wc_job=False):
        wc_product_categ_obj = self.env['wc.category.cft']
        categ_ids = []
        for wc_category in wc_categories:
            wc_product_categ = wc_product_categ_obj.search(
                [('wc_categ_id', '=', wc_category.get('id')), ('wc_instance_id', '=', wc_instance.id)], limit=1)
            if not wc_product_categ:
                wc_product_categ = wc_product_categ_obj.search(
                    [('slug', '=', wc_category.get('slug')), ('wc_instance_id', '=', wc_instance.id)], limit=1)
            if wc_product_categ:
                wc_product_categ.write({'wc_categ_id': wc_category.get('id'), 'name': wc_category.get('name'),
                                        'display': wc_category.get('display'), 'slug': wc_category.get('slug'),
                                        'avail_in_wc': True})
                wc_product_categ_obj.sync_product_category(wc_instance, wc_categ=wc_category.get('id'),
                                                           sync_images_with_product=sync_images_with_product)
                categ_ids.append(wc_product_categ.id)
            else:
                wc_product_categ = wc_product_categ_obj.create(
                    {'wc_categ_id': wc_category.get('id'), 'name': wc_category.get('name'),
                     'display': wc_category.get('display'), 'slug': wc_category.get('slug'),
                     'wc_instance_id': wc_instance.id, 'avail_in_wc': True})
                wc_product_categ_obj.sync_product_category(wc_instance, wc_categ=wc_category.get('id'),
                                                           sync_images_with_product=sync_images_with_product)
                wc_product_categ and categ_ids.append(wc_product_categ.id)
        return categ_ids

    def sync_wc_product_tags(self, wcapi, wc_instance, wc_tags):
        obj_wc_product_tags = self.env['wc.tags.cft']
        tag_ids = []
        for wc_tag in wc_tags:
            wc_product_tag = obj_wc_product_tags.search(
                [('wc_tag_id', '=', wc_tag.get('id')), ('wc_instance_id', '=', wc_instance.id)], limit=1)
            if not wc_product_tag:
                wc_product_tag = obj_wc_product_tags.search(
                    [('slug', '=', wc_tag.get('slug')), ('wc_instance_id', '=', wc_instance.id)], limit=1)
            if wc_product_tag:
                wc_product_tag.write(
                    {'name': wc_tag.get('name'), 'slug': wc_tag.get('slug'), 'avail_in_wc': True})
                tag_ids.append(wc_product_tag.id)
            else:
                wc_product_tag = obj_wc_product_tags.create(
                    {'wc_tag_id': wc_tag.get('id'), 'name': wc_tag.get('name'), 'slug': wc_tag.get('slug'),
                     'wc_instance_id': wc_instance.id, 'avail_in_wc': True})
                wc_product_tag and tag_ids.append(wc_product_tag.id)
        return tag_ids

    def sync_wc_attribute_term(self, wc_instance, wc_job=False):
        obj_wc_attribute = self.env['wc.product.attribute.cft']
        obj_wc_attribute_term = self.env['wc.product.attribute.cft.term']
        odoo_attribute_value_obj = self.env['product.attribute.value']
        wcapi = wc_instance.wc_connect()
        wc_attributes = obj_wc_attribute.search([])
        for wc_attribute in wc_attributes:
            response = wcapi.get("products/attributes/%s/terms?per_page=100" % (wc_attribute.wc_attribute_id),
                                 wc_job=wc_job)
            if not response:
                return False
            attributes_term_data = response.json()
            total_pages = response and response.headers.get('x-wp-totalpages') or 1
            if int(total_pages) >= 2:
                for page in range(2, int(total_pages) + 1):
                    page_res = wcapi.get(
                        "products/attributes/%s/terms?per_page=100&page=%s" % (wc_attribute.wc_attribute_id, page))
                    if page_res:
                        return False
                    attributes_term_data = attributes_term_data + page_res.json()
            for attribute_term in attributes_term_data:
                wc_attribute_term = obj_wc_attribute_term.search(
                    [('wc_attribute_term_id', '=', attribute_term.get('id')),
                     ('wc_instance_id', '=', wc_instance.id), ('avail_in_wc', '=', True)], limit=1)
                if wc_attribute_term:
                    continue
                odoo_attribute_value = odoo_attribute_value_obj.search(
                    [('name', '=ilike', attribute_term.get('name')),
                     ('attribute_id', '=', wc_attribute.attribute_id.id)], limit=1)
                if not odoo_attribute_value:
                    odoo_attribute_value = odoo_attribute_value.with_context(active_id=False).create(
                        {'name': attribute_term.get('name'), 'attribute_id': wc_attribute.attribute_id.id})
                wc_attribute_term = obj_wc_attribute_term.search(
                    [('attribute_value_id', '=', odoo_attribute_value.id),
                     ('attribute_id', '=', wc_attribute.attribute_id.id),
                     ('wc_attribute_id', '=', wc_attribute.id), ('wc_instance_id', '=', wc_instance.id),
                     ('avail_in_wc', '=', False)], limit=1)
                if wc_attribute_term:
                    wc_attribute_term.write(
                        {'wc_attribute_term_id': attribute_term.get('id'), 'count': attribute_term.get('count'),
                         'slug': attribute_term.get('slug'), 'avail_in_wc': True})
                else:
                    obj_wc_attribute_term.create(
                        {'name': attribute_term.get('name'), 'wc_attribute_term_id': attribute_term.get('id'),
                         'slug': attribute_term.get('slug'), 'wc_instance_id': wc_instance.id,
                         'attribute_value_id': odoo_attribute_value.id,
                         'wc_attribute_id': wc_attribute.wc_attribute_id,
                         'attribute_id': wc_attribute.attribute_id.id,
                         'avail_in_wc': True, 'count': attribute_term.get('count')})
        return True

    def sync_wc_attribute(self, wc_instance, wc_job=False):
        obj_wc_attribute = self.env['wc.product.attribute.cft']
        odoo_attribute_obj = self.env['product.attribute']
        wcapi = wc_instance.wc_connect()
        response = wcapi.get("products/attributes?per_page=100", wc_job=wc_job)
        if not response:
            return False
        attributes_data = response.json()
        total_pages = response and response.headers.get('x-wp-totalpages') or 1
        if int(total_pages) >= 2:
            for page in range(2, int(total_pages) + 1):
                page_res = wcapi.get('products/attributes?per_page=100&page=%s' % (page))
                if not page_res:
                    continue
                attributes_data = attributes_data + page_res.json()
        for attribute in attributes_data:
            wc_attribute = obj_wc_attribute.search(
                [('wc_attribute_id', '=', attribute.get('id')), ('wc_instance_id', '=', wc_instance.id),
                 ('avail_in_wc', '=', True)], limit=1)
            if wc_attribute:
                continue
            odoo_attribute = odoo_attribute_obj.search([('name', '=ilike', attribute.get('name'))], limit=1)
            if not odoo_attribute:
                odoo_attribute = odoo_attribute.create({'name': attribute.get('name')})
            wc_attribute = obj_wc_attribute.search(
                [('attribute_id', '=', odoo_attribute.id), ('wc_instance_id', '=', wc_instance.id),
                 ('avail_in_wc', '=', False)], limit=1)
            if wc_attribute:
                wc_attribute.write({'wc_attribute_id': attribute.get('id'), 'order_by': attribute.get('order_by'),
                                    'slug': attribute.get('slug'), 'avail_in_wc': True,
                                    'has_archives': attribute.get('has_archives')})
            else:
                obj_wc_attribute.create({'name': attribute.get('name'), 'wc_attribute_id': attribute.get('id'),
                                         'order_by': attribute.get('order_by'),
                                         'slug': attribute.get('slug'), 'wc_instance_id': wc_instance.id,
                                         'attribute_id': odoo_attribute.id,
                                         'avail_in_wc': True, 'has_archives': attribute.get('has_archives')})
        self.sync_wc_attribute_term(wc_instance, wc_job=wc_job)
        return True

    def export_product_attributes_in_wc(self, wc_instance, attribute, wc_job=False):
        wcapi = wc_instance.wc_connect()
        obj_wc_attribute = self.env['wc.product.attribute.cft']
        wc_attribute = obj_wc_attribute.search(
            [('attribute_id', '=', attribute.id), ('wc_instance_id', '=', wc_instance.id),
             ('avail_in_wc', '=', True)], limit=1)
        if wc_attribute and wc_attribute.wc_attribute_id:
            return {attribute.id: wc_attribute.wc_attribute_id}
        attribute_data = {'name': attribute.name,
                          'type': 'select',
                          }
        attribute_res = wcapi.post("products/attributes", attribute_data, wc_job=wc_job)
        if not hasattr(attribute_res, 'status_code') and not attribute_res:
            return False
        if attribute_res.status_code == 400:
            self.sync_wc_attribute(wc_instance, wc_job=wc_job)
            wc_attribute = obj_wc_attribute.search(
                [('attribute_id', '=', attribute.id), ('wc_instance_id', '=', wc_instance.id),
                 ('avail_in_wc', '=', True)], limit=1)
            if wc_attribute and wc_attribute.wc_attribute_id:
                return {attribute.id: wc_attribute.wc_attribute_id}
        attribute_response = attribute_res.json()
        wc_attribute_id = attribute_response.get('id')
        wc_attribute_name = attribute_response.get('name')
        wc_attribute_slug = attribute_response.get('slug')
        wc_attribute_order_by = attribute_response.get('order_by')
        has_archives = attribute_response.get('has_archives')
        obj_wc_attribute.create(
            {'name': attribute and attribute.name or wc_attribute_name, 'wc_attribute_id': wc_attribute_id,
             'order_by': wc_attribute_order_by,
             'slug': wc_attribute_slug, 'wc_instance_id': wc_instance.id, 'attribute_id': attribute.id,
             'avail_in_wc': True, 'has_archives': has_archives})
        return {attribute.id: wc_attribute_id}

    def set_variant_sku(self, wc_instance, result, product_template, sync_price_with_product=False):
        product_attribute_obj = self.env['product.attribute']
        product_attribute_value_obj = self.env['product.attribute.value']
        odoo_product_obj = self.env['product.product']
        wc_attribute_obj = self.env['wc.product.attribute.cft']
        wc_attribute_term_obj = self.env['wc.product.attribute.cft.term']

        for variation in result.get('variations'):
            sku = variation.get('sku')
            price = variation.get('regular_price')
            attribute_value_ids = []
            domain = []
            odoo_product = False
            variation_attributes = variation.get('attributes')

            for variation_attribute in variation_attributes:
                attribute_val = variation_attribute.get('option')
                attribute_name = variation_attribute.get('name')
                if wc_instance.attribute_type == 'text':
                    for attribute in result.get('attributes'):
                        if attribute.get('variation') and attribute.get('name'):
                            if attribute.get('name').replace(" ", "-").lower() == attribute_name:
                                attribute_name = attribute.get('name')
                                break
                    product_attribute = product_attribute_obj.search([('name', '=ilike', attribute_name)], limit=1)
                    if product_attribute:
                        product_attribute_value = product_attribute_value_obj.search(
                            [('attribute_id', '=', product_attribute.id), ('name', '=', attribute_val)], limit=1)
                        product_attribute_value and attribute_value_ids.append(product_attribute_value.id)
                if wc_instance.attribute_type == 'select':
                    wc_product_attribute = wc_attribute_obj.search([('name', '=ilike', attribute_name)], limit=1)
                    if wc_product_attribute:
                        wc_product_attribute_term = wc_attribute_term_obj.search(
                            [('wc_attribute_id', '=', wc_product_attribute.wc_attribute_id),
                             ('name', '=', attribute_val)], limit=1)
                        if not wc_product_attribute_term:
                            wc_product_attribute_term = wc_attribute_term_obj.search(
                                [('wc_attribute_id', '=', wc_product_attribute.wc_attribute_id),
                                 ('slug', '=', attribute_val)], limit=1)
                        wc_product_attribute_term and attribute_value_ids.append(
                            wc_product_attribute_term.attribute_value_id.id)

            for attribute_value_id in attribute_value_ids:
                tpl = ('product_template_attribute_value_ids.product_attribute_value_id', '=', attribute_value_id)
                domain.append(tpl)
            domain and domain.append(('product_tmpl_id', '=', product_template.id))
            if domain:
                odoo_product = odoo_product_obj.search(domain)
            odoo_product and odoo_product.write({'default_code': sku})
            if odoo_product and sync_price_with_product:
                pricelist_item = self.env['product.pricelist.item'].search(
                    [('pricelist_id', '=', wc_instance.pricelist_id.id), ('product_id', '=', odoo_product.id)], limit=1)
                if not pricelist_item:
                    wc_instance.pricelist_id.write({
                        'item_ids': [(0, 0, {
                            'applied_on': '0_product_variant',
                            'product_id': odoo_product.id,
                            'compute_price': 'fixed',
                            'fixed_price': price})]
                    })
                else:
                    pricelist_item.write({'fixed_price': price})
                odoo_product.write({'list_price': price})
        return True

    def create_variant_product(self, result, wc_instance):
        product_attribute_obj = self.env['product.attribute']
        product_attribute_value_obj = self.env['product.attribute.value']
        product_template_obj = self.env['product.template']

        template_title = result.get('name')
        attrib_line_vals = []
        for attrib in result.get('attributes'):
            if not attrib.get('variation'):
                continue
            attrib_name = attrib.get('name')
            attrib_values = attrib.get('options')
            attribute = product_attribute_obj.search([('name', '=ilike', attrib_name)], limit=1)
            if not attribute:
                attribute = product_attribute_obj.create({'name': attrib_name})
            attr_val_ids = []

            for attrib_vals in attrib_values:
                attrib_value = product_attribute_value_obj.search(
                    [('attribute_id', '=', attribute.id), ('name', '=', attrib_vals)], limit=1)
                if not attrib_value:
                    attrib_value = product_attribute_value_obj.with_context(active_id=False).create(
                        {'attribute_id': attribute.id, 'name': attrib_vals})
                attr_val_ids.append(attrib_value.id)

            if attr_val_ids:
                attribute_line_ids_data = [0, False,
                                           {'attribute_id': attribute.id, 'value_ids': [[6, False, attr_val_ids]]}]
                attrib_line_vals.append(attribute_line_ids_data)
        if attrib_line_vals:
            product_template = product_template_obj.create({'name': template_title,
                                                            'type': 'product',
                                                            'attribute_line_ids': attrib_line_vals,
                                                            'description_sale': result.get('description', '')})
            self.set_variant_sku(wc_instance, result, product_template,
                                 sync_price_with_product=wc_instance.sync_price_with_product)
        else:
            return False
        return True

    def set_variant_images(self, odoo_product_images):
        for odoo_product_image in odoo_product_images:
            binary_img_data = odoo_product_image.get('image', False)
            odoo_product = odoo_product_image.get('odoo_product', False)
            if odoo_product:
                odoo_product.write({'image_1920': binary_img_data})

    def is_product_importable(self, result, wc_instance, odoo_product, wc_product):
        wc_skus = []
        odoo_skus = []
        variations = result.get('variations')
        template_title = result.get('name')
        product_count = len(variations)
        importable = True
        message = ""
        if not odoo_product and not wc_product:
            if product_count != 0:
                attributes = 1
                for attribute in result.get('attributes'):
                    if attribute.get('variation'):
                        attributes *= len(attribute.get('options'))
            product_attributes = {}
            for variantion in variations:
                sku = variantion.get("sku")
                attributes = variantion.get('attributes')
                attributes and product_attributes.update({sku: attributes})
                sku and wc_skus.append(sku)
            if not product_attributes and result.get('type') == 'variable':
                message = "Attributes are not set in any variation of Product: %s and ID: %s." % (
                    template_title, result.get("id"))
                importable = False
                return importable, message
            if wc_skus:
                wc_skus = list(filter(lambda x: len(x) > 0, wc_skus))
            total_wc_sku = len(set(wc_skus))
            if not len(wc_skus) == total_wc_sku:
                message = "Duplicate SKU found in Product: %s and ID: %s." % (template_title, result.get("id"))
                importable = False
                return importable, message
        wc_skus = []
        if odoo_product:
            odoo_template = odoo_product.product_tmpl_id
            if not (product_count == 0 and odoo_template.product_variant_count == 1):
                if product_count == odoo_template.product_variant_count:
                    for wc_sku, odoo_sku in zip(result.get('variations'), odoo_template.product_variant_ids):
                        wc_skus.append(wc_sku.get('sku'))
                        odoo_sku.default_code and odoo_skus.append(odoo_sku.default_code)

                    wc_skus = list(filter(lambda x: len(x) > 0, wc_skus))
                    odoo_skus = list(filter(lambda x: len(x) > 0, odoo_skus))

                    total_wc_sku = len(set(wc_skus))
                    if not len(wc_skus) == total_wc_sku:
                        message = "Duplicate SKU found in Product: %s and ID: %s." % (template_title, result.get("id"))
                        importable = False
                        return importable, message
        if wc_product:
            wc_skus = []
            for wc_sku in result.get('variations'):
                wc_skus.append(wc_sku.get('sku'))

            total_wc_sku = len(set(wc_skus))
            if not len(wc_skus) == total_wc_sku:
                message = "Duplicate SKU found in Product: %s and ID: %s." % (template_title, result.get("id"))
                importable = False
                return importable, message
        return importable, message

    def sync_gallery_images(self, wc_instance, result, wc_template, odoo_product_images, wc_product_img):
        images = result.get('images')
        existing_gallery_img_keys = {}
        img_position = 0
        for gallery_img in wc_template.wc_gallery_image_ids:
            if not gallery_img.image:
                continue
            key = hashlib.md5(gallery_img.image).hexdigest()
            if not key:
                continue
            existing_gallery_img_keys.update({key: gallery_img})
        for image in images:
            if str(image.get('name').encode('utf-8')) == 'Placeholder' or not image.get('id'):
                continue
            image_id = image.get('id')
            res_image_src = image.get('src')
            if image.get('position'):
                position = image.get('position')
            else:
                position = img_position
                img_position += 1
            binary_img_data = False
            if res_image_src:
                try:
                    res_img = requests.get(res_image_src, stream=True, verify=False, timeout=10)
                    if res_img.status_code == 200:
                        binary_img_data = base64.b64encode(res_img.content)
                        key = hashlib.md5(binary_img_data).hexdigest()
                        if key in existing_gallery_img_keys:
                            gallery_image = existing_gallery_img_keys.get(key)
                            gallery_image.write({'sequence': position, 'wc_image_id': image_id})
                            continue
                        if position == 0:
                            wc_template.product_tmpl_id.write({'image_1920': binary_img_data})
                            if result.get('variations'):
                                odoo_product_images and self.set_variant_images(odoo_product_images)
                except Exception:
                    pass

            if res_image_src:
                if position == 0:
                    wc_template.product_tmpl_id.write({'image_1920': binary_img_data})
                    if result.get('variations'):
                        odoo_product_images and self.set_variant_images(odoo_product_images)
                wc_product_tmp_img = wc_product_img.search(
                    [('wc_product_tmpl_id', '=', wc_template.id), ('wc_instance_id', '=', wc_instance.id),
                     ('wc_image_id', '=', image_id)], limit=1)
                if wc_product_tmp_img:
                    wc_product_tmp_img.write({'image': binary_img_data, 'sequence': position})
                else:
                    wc_product_img.create({'wc_instance_id': wc_instance.id, 'sequence': position,
                                           'wc_product_tmpl_id': wc_template.id, 'image': binary_img_data,
                                           'wc_image_id': image_id})
        return True

    @api.model
    def create_wc_product(self, wc_product_obj, vals, result, wc_instance):
        return wc_product_obj.create(vals)

    @api.model
    def update_wc_product(self, vals, wc_product, result, wc_instance):
        return wc_product.write(vals)

    @api.model
    def create_wc_template(self, vals, result, wc_instance):
        return self.create(vals)

    @api.model
    def update_wc_template(self, vals, wc_template, result, wc_instance):
        return wc_template.write(vals)

    def import_wc_products(self, wc_instance, wc_tmpl_ids=False, update_price=False,
                           sync_images_with_product=False, update_template=False):
        odoo_product_images = []
        wc_job = self.env['wc.process.job.cft'].create(
            {'wc_instance_id': wc_instance.id, 'process_type': 'product', 'operation_type': 'import_sync',
             'message': 'Process for Import/Sync Products'})
        if wc_instance.attribute_type == 'select':
            self.sync_wc_attribute(wc_instance, wc_job=wc_job)
        wc_product_obj = self.env['wc.product.product.cft']
        wc_product_img = self.env['wc.product.image.cft']
        product_template_obj = self.env['product.template']
        odoo_product_obj = self.env['product.product']
        wcapi = wc_instance.wc_connect()

        is_importable = True
        categ_and_tag_imported = True
        if wc_tmpl_ids:
            if self._context.get('from_so'):
                res = wcapi.get(
                    'products?include={0}&per_page=100'.format(wc_tmpl_ids),
                    wc_job=wc_job)
            else:
                res = wcapi.get(
                    'products?include={0}&per_page=100'.format(",".join([wcp.wc_tmpl_id for wcp in wc_tmpl_ids])),
                    wc_job=wc_job)
        else:
            res = wcapi.get('products?per_page=100', wc_job=wc_job)
        if not res:
            return False
        total_pages = res.headers.get('x-wp-totalpages', 0)
        results = res.json()
        if int(total_pages) >= 2:
            for page in range(2, int(total_pages) + 1):
                if wc_tmpl_ids:
                    page_res = wcapi.get('products?include={0}&per_page=100&page={1}'.format(
                        ",".join([wcp.wc_tmpl_id for wcp in wc_tmpl_ids]), page),
                        wc_job=wc_job)
                else:
                    page_res = wcapi.get('products?per_page=100&page=%s' % (page), wc_job=wc_job)
                if not page_res:
                    continue
                results = results + page_res.json()
        if wc_instance.wc_version != 'v1':
            for result in results:
                variants = []
                if not result.get('variations'):
                    result.update({'variations': variants})
                    continue
                wc_id = result.get('id')
                variant_response = wcapi.get('products/%s/variations?per_page=100' % (wc_id), wc_job=wc_job)
                if not variant_response:
                    return False
                variants += variant_response.json()
                total_pages = variant_response.headers.get('x-wp-totalpages', 0)
                if int(total_pages) >= 2:
                    for page in range(2, int(total_pages) + 1):
                        page_res = wcapi.get('products/%s/variations?per_page=100&page=%s' % (wc_id, page),
                                             wc_job=wc_job)
                        if not page_res:
                            continue
                        variants += page_res.json()
                result.update({'variations': variants})
        if wc_tmpl_ids:
            categ_and_tag_imported = False
        if categ_and_tag_imported:
            self.env['wc.category.cft'].sync_product_category(wc_instance,
                                                              sync_images_with_product=sync_images_with_product)
            self.env['wc.tags.cft'].sync_product_tags(wc_instance)
        if not results:
            return False
        for result in results:
            odoo_product = False
            wc_tmpl_id = result.get('id')
            template_title = result.get('name')
            template_created_at = result.get('date_created',False) and result.get('date_created').replace("T", " ")
            template_updated_at = result.get('date_modified',False) and result.get('date_modified').replace("T", " ")

            if template_created_at and template_created_at.startswith('-'):
                template_created_at = template_created_at[1:]
            if template_updated_at and template_updated_at.startswith('-'):
                template_updated_at = template_updated_at[1:]

            short_description = result.get('short_description')
            description = result.get('description')
            status = result.get('status')
            tax_status = result.get('tax_status')

            taxable = True
            if tax_status != 'taxable':
                taxable = False
            website_published = False
            if status == 'publish':
                website_published = True

            tmpl_info = {'name': template_title, 'created_at': template_created_at or False,
                         'updated_at': template_updated_at or False,
                         'short_description': short_description, 'description': description,
                         'website_published': website_published, 'taxable': taxable}

            wc_template = self.search([('wc_tmpl_id', '=', wc_tmpl_id), ('wc_instance_id', '=', wc_instance.id)],
                                      limit=1)
            if wc_template and not update_template:
                continue
            update_template = False
            onetime_call = False
            for variation in result.get('variations'):
                variant_id = variation.get('id')
                sku = variation.get('sku')
                wc_product = wc_product_obj.search(
                    [('variant_id', '=', variant_id), ('wc_instance_id', '=', wc_instance.id)], limit=1)
                if not wc_product:
                    wc_product = wc_product_obj.search(
                        [('default_code', '=', sku), ('wc_instance_id', '=', wc_instance.id)], limit=1)
                if not wc_product:
                    wc_product = wc_product_obj.search(
                        [('product_id.default_code', '=', sku), ('wc_instance_id', '=', wc_instance.id)], limit=1)
                if not wc_product:
                    odoo_product = odoo_product_obj.search([('default_code', '=', sku)], limit=1)
                if wc_product:
                    odoo_product = wc_product.product_id

                is_importable, message = self.is_product_importable(result, wc_instance, odoo_product, wc_product)
                if not is_importable:
                    wc_job.env['wc.process.job.cft.line'].create(
                        {'wc_job_id': wc_job.id, 'message': message})
                    break
                if not odoo_product and not wc_product and not wc_template:
                    if wc_instance.auto_create_product:
                        if not onetime_call:
                            self.create_variant_product(result, wc_instance)
                            odoo_product = odoo_product_obj.search([('default_code', '=', sku)], limit=1)
                            onetime_call = True
                    else:
                        message = "%s Product Not found for sku %s" % (template_title, sku)
                        wc_job.env['wc.process.job.cft.line'].create(
                            {'wc_job_id': wc_job.id, 'message': message})
                        continue
                if not odoo_product:
                    continue
                var_img = False
                price = variation.get('regular_price')
                if sync_images_with_product:
                    var_images = variation.get('image')
                    if wc_instance.wc_version != 'v1':
                        var_images = [var_images]
                    for var_image in var_images:
                        if not var_image:
                            continue
                        if str(var_image.get('name').encode('utf-8')) == 'Placeholder' or not var_image.get('id'):
                            continue
                        if var_image.get('position') == 0:
                            var_image_src = var_image.get('src')
                            if var_image_src:
                                try:
                                    res_img = requests.get(var_image_src, stream=True, verify=False, timeout=10)
                                    if res_img.status_code == 200:
                                        var_img = base64.b64encode(res_img.content)
                                except Exception:
                                    pass
                created_at = variation.get('date_created').replace("T", " ")
                updated_at = variation.get('date_modified').replace("T", " ")
                if created_at and created_at.startswith('-'):
                    created_at = created_at[1:]
                if updated_at and updated_at.startswith('-'):
                    updated_at = updated_at[1:]
                variant_info = {'name': template_title, 'default_code': sku, 'created_at': created_at or False,
                                'updated_at': updated_at or False, }
                if not wc_product:
                    if not wc_template:
                        wc_categories = result.get('categories')
                        if not categ_and_tag_imported:
                            categ_ids = self.sync_wc_product_categ(wcapi, wc_instance, wc_categories,
                                                                   sync_images_with_product, wc_job=wc_job)
                        else:
                            wc_categs = []
                            for wc_category in wc_categories:
                                wc_categ = wc_category.get('id') and self.env['wc.category.cft'].search(
                                    [('wc_categ_id', '=', wc_category.get('id'))], limit=1)
                                wc_categ and wc_categs.append(wc_categ.id)
                            categ_ids = wc_categs and wc_categs or []
                        wc_tags = result.get('tags')
                        if not categ_and_tag_imported:
                            tag_ids = self.sync_wc_product_tags(wcapi, wc_instance, wc_tags)
                        else:
                            product_tags = []
                            for wc_tag in wc_tags:
                                product_tag = wc_tag.get('id') and self.env['wc.tags.cft'].search(
                                    [('wc_tag_id', '=', wc_tag.get('id'))], limit=1)
                                product_tag and product_tags.append(product_tag.id)
                            tag_ids = product_tags and product_tags or []
                        tmpl_info.update(
                            {'product_tmpl_id': odoo_product.product_tmpl_id.id, 'wc_instance_id': wc_instance.id,
                             'wc_tmpl_id': wc_tmpl_id, 'taxable': taxable,
                             'avail_in_wc': True, 'wc_categ_ids': [(6, 0, categ_ids)],
                             'wc_tag_ids': [(6, 0, tag_ids)],
                             })
                        wc_template = self.create_wc_template(tmpl_info, result, wc_instance)

                    variant_info.update(
                        {'product_id': odoo_product.id,
                         'name': template_title,
                         'variant_id': variant_id,
                         'wc_template_id': wc_template.id,
                         'wc_instance_id': wc_instance.id,
                         'avail_in_wc': True,
                         })
                    wc_product = self.create_wc_product(wc_product_obj, variant_info, result, wc_instance)
                    if sync_images_with_product:
                        odoo_product_images.append(
                            {'odoo_product': odoo_product, 'image': var_img if wc_product else None, 'sku': sku})
                    if update_price:
                        pricelist_item = self.env['product.pricelist.item'].search(
                            [('pricelist_id', '=', wc_instance.pricelist_id.id), ('product_id', '=', odoo_product.id)],
                            limit=1)
                        if not pricelist_item:
                            wc_instance.pricelist_id.write({
                                'item_ids': [(0, 0, {
                                    'applied_on': '0_product_variant',
                                    'product_id': odoo_product.id,
                                    'compute_price': 'fixed',
                                    'fixed_price': price})]
                            })
                        else:
                            pricelist_item.write(
                                {'applied_on': '0_product_variant', 'compute_price': 'fixed', 'fixed_price': price})
                else:
                    if not update_template:
                        wc_categories = result.get('categories')
                        if not categ_and_tag_imported:
                            categ_ids = self.sync_wc_product_categ(wcapi, wc_instance, wc_categories,
                                                                   sync_images_with_product, wc_job=wc_job)
                        else:
                            wc_categs = []
                            for wc_category in wc_categories:
                                wc_categ = wc_category.get('id') and self.env['wc.category.cft'].search(
                                    [('wc_categ_id', '=', wc_category.get('id'))], limit=1)
                                wc_categ and wc_categs.append(wc_categ.id)
                            categ_ids = wc_categs and wc_categs or []

                        wc_tags = result.get('tags')
                        if not categ_and_tag_imported:
                            tag_ids = self.sync_wc_product_tags(wcapi, wc_instance, wc_tags)
                        else:
                            product_tags = []
                            for wc_tag in wc_tags:
                                product_tag = wc_tag.get('id') and self.env['wc.tags.cft'].search(
                                    [('wc_tag_id', '=', wc_tag.get('id'))], limit=1)
                                product_tag and product_tags.append(product_tag.id)
                            tag_ids = product_tags and product_tags or []
                        tmpl_info.update({
                            'wc_tmpl_id': wc_tmpl_id, 'taxable': taxable,
                            'avail_in_wc': True,
                            'wc_categ_ids': [(6, 0, categ_ids)],
                            'wc_tag_ids': [(6, 0, tag_ids)],
                        })
                        update_template = True
                        if not wc_template:
                            wc_template = wc_product.wc_template_id
                        self.update_wc_template(tmpl_info, wc_template, result, wc_instance)
                    variant_info.update({
                        'variant_id': variant_id,
                        'wc_template_id': wc_template.id,
                        'wc_instance_id': wc_instance.id,
                        'avail_in_wc': True,
                    })
                    self.update_wc_product(variant_info, wc_product, result, wc_instance)
                    if update_price:
                        pricelist_item = self.env['product.pricelist.item'].search(
                            [('pricelist_id', '=', wc_instance.pricelist_id.id),
                             ('product_id', '=', wc_product.product_id.id)], limit=1)
                        if not pricelist_item:
                            wc_instance.pricelist_id.write({
                                'item_ids': [(0, 0, {
                                    'applied_on': '0_product_variant',
                                    'product_id': wc_product.product_id.id,
                                    'compute_price': 'fixed',
                                    'fixed_price': price})]
                            })
                        else:
                            pricelist_item.write(
                                {'applied_on': '0_product_variant', 'compute_price': 'fixed', 'fixed_price': price})
                    if sync_images_with_product:
                        odoo_product_images.append(
                            {'odoo_product': odoo_product, 'image': var_img if wc_product else None, 'sku': sku})
                        if var_img:
                            odoo_product.image = var_img
            if not result.get('variations'):
                sku = result.get('sku')
                price = result.get('regular_price')
                wc_product = wc_product_obj.search(
                    [('variant_id', '=', wc_tmpl_id), ('wc_instance_id', '=', wc_instance.id)], limit=1)
                if not wc_product:
                    wc_product = wc_product_obj.search(
                        [('default_code', '=', sku), ('wc_instance_id', '=', wc_instance.id)], limit=1)
                if not wc_product:
                    wc_product = wc_product_obj.search(
                        [('product_id.default_code', '=', sku), ('wc_instance_id', '=', wc_instance.id)], limit=1)
                if not wc_product:
                    odoo_product = odoo_product_obj.search([('default_code', '=', sku)], limit=1)

                is_importable, message = self.is_product_importable(result, wc_instance, odoo_product, wc_product)
                if not is_importable:
                    wc_job.env['wc.process.job.cft.line'].create(
                        {'wc_job_id': wc_job.id, 'message': message})
                    continue

                if not odoo_product and not wc_product:
                    if sku:
                        if wc_instance.auto_create_product:
                            vals = {'name': template_title,
                                    'default_code': sku,
                                    'type': 'product',
                                    }
                            product_template = product_template_obj.create(vals)
                            odoo_product = product_template.product_variant_ids
                            if wc_instance.sync_price_with_product:
                                pricelist_item = self.env['product.pricelist.item'].search(
                                    [('pricelist_id', '=', wc_instance.pricelist_id.id),
                                     ('product_id', '=', odoo_product.id)], limit=1)
                                if not pricelist_item:
                                    wc_instance.pricelist_id.write({
                                        'item_ids': [(0, 0, {
                                            'applied_on': '0_product_variant',
                                            'product_id': odoo_product.id,
                                            'compute_price': 'fixed',
                                            'fixed_price': price})]
                                    })
                                else:
                                    pricelist_item and pricelist_item.write(
                                        {'applied_on': '0_product_variant', 'compute_price': 'fixed',
                                         'fixed_price': price})
                                odoo_product.write({'list_price': price})
                        else:
                            message = "%s Product  Not found for sku %s" % (template_title, sku)
                            wc_job.env['wc.process.job.cft.line'].create(
                                {'wc_job_id': wc_job.id, 'message': message})
                            continue
                    else:
                        message = "SKU not set in Product: %s and ID: %s." % (template_title, result.get('id'))
                        wc_job.env['wc.process.job.cft.line'].create(
                            {'wc_job_id': wc_job.id, 'message': message})
                        continue
                categ_ids = []
                tag_ids = []
                if not categ_and_tag_imported:
                    wc_categories = result.get('categories')
                    if not categ_and_tag_imported:
                        categ_ids = self.sync_wc_product_categ(wcapi, wc_instance, wc_categories,
                                                               sync_images_with_product, wc_job=wc_job)
                    else:
                        wc_categs = []
                        for wc_category in wc_categories:
                            wc_categ = wc_category.get('id') and self.env['wc.category.cft'].search(
                                [('wc_categ_id', '=', wc_category.get('id'))], limit=1)
                            wc_categ and wc_categs.append(wc_categ.id)
                        categ_ids = wc_categs and wc_categs or []

                    wc_tags = result.get('tags')
                    if not categ_and_tag_imported:
                        tag_ids = self.sync_wc_product_tags(wcapi, wc_instance, wc_tags)
                    else:
                        product_tags = []
                        for wc_tag in wc_tags:
                            product_tag = wc_tag.get('id') and self.env['wc.tags.cft'].search(
                                [('wc_tag_id', '=', wc_tag.get('id'))], limit=1)
                            product_tag and product_tags.append(product_tag.id)
                        tag_ids = product_tags and product_tags or []
                if not wc_product:
                    if not wc_template:
                        tmpl_info.update(
                            {'product_tmpl_id': odoo_product.product_tmpl_id.id, 'wc_instance_id': wc_instance.id,
                             'wc_tmpl_id': wc_tmpl_id, 'taxable': taxable,
                             'wc_categ_ids': [(6, 0, categ_ids)],
                             'wc_tag_ids': [(6, 0, tag_ids)],
                             'avail_in_wc': True,
                             })
                        wc_template = self.create_wc_template(tmpl_info, result, wc_instance)
                    variant_info = {'name': template_title, 'default_code': sku, 'created_at': template_created_at,
                                    'updated_at': template_updated_at, 'product_id': odoo_product.id,
                                    'variant_id': wc_tmpl_id, 'wc_template_id': wc_template.id,
                                    'wc_instance_id': wc_instance.id, 'avail_in_wc': True}
                    wc_product = wc_product_obj.create(variant_info)
                    if update_price:
                        pricelist_item = self.env['product.pricelist.item'].search(
                            [('pricelist_id', '=', wc_instance.pricelist_id.id), ('product_id', '=', odoo_product.id)],
                            limit=1)
                        if not pricelist_item:
                            wc_instance.pricelist_id.write({
                                'item_ids': [(0, 0, {
                                    'applied_on': '0_product_variant',
                                    'product_id': odoo_product.id,
                                    'compute_price': 'fixed',
                                    'fixed_price': price})]
                            })
                        else:
                            pricelist_item.write(
                                {'applied_on': '0_product_variant', 'compute_price': 'fixed', 'fixed_price': price})
                else:
                    if not update_template:
                        tmpl_info.update({
                            'wc_tmpl_id': wc_tmpl_id, 'taxable': taxable,
                            'wc_categ_ids': [(6, 0, categ_ids)],
                            'wc_tag_ids': [(6, 0, tag_ids)],
                            'avail_in_wc': True,
                        })
                        if not wc_template:
                            wc_template = wc_product.wc_template_id
                        self.update_wc_template(tmpl_info, wc_template, result, wc_instance)
                    variant_info = {'name': template_title, 'default_code': sku, 'created_at': template_created_at,
                                    'updated_at': template_updated_at,
                                    'variant_id': wc_tmpl_id, 'wc_template_id': wc_template.id,
                                    'wc_instance_id': wc_instance.id,
                                    'avail_in_wc': True}
                    self.update_wc_product(variant_info, wc_product, result, wc_instance)
                    if update_price:
                        pricelist_item = self.env['product.pricelist.item'].search(
                            [('pricelist_id', '=', wc_instance.pricelist_id.id),
                             ('product_id', '=', wc_product.product_id.id)], limit=1)
                        if not pricelist_item:
                            wc_instance.pricelist_id.write({
                                'item_ids': [(0, 0, {
                                    'applied_on': '0_product_variant',
                                    'product_id': wc_product.product_id.id,
                                    'compute_price': 'fixed',
                                    'fixed_price': price})]
                            })
                        else:
                            pricelist_item.write(
                                {'applied_on': '0_product_variant', 'compute_price': 'fixed', 'fixed_price': price})
            if is_importable and wc_template and sync_images_with_product:
                self.sync_gallery_images(wc_instance, result, wc_template, odoo_product_images, wc_product_img)
            self._cr.commit()
        return True

    @api.model
    def update_wc_product_image(self, wc_instance, wc_templates):
        wc_job = self.env['wc.process.job.cft'].create(
            {'wc_instance_id': wc_instance.id, 'process_type': 'product', 'operation_type': 'update',
             'message': 'Process for Update Products Images'})
        wcapi = wc_instance.wc_connect()
        batches = []
        wc_template_ids = wc_templates.ids
        total_wc_templates = len(wc_template_ids)
        start, end = 0, 100
        if total_wc_templates > 100:
            while True:
                w_template_ids = wc_template_ids[start:end]
                if not w_template_ids:
                    break
                temp = end + 100
                start, end = end, temp
                if w_template_ids:
                    w_templates = self.browse(w_template_ids)
                    batches.append(w_templates)
        else:
            batches.append(wc_templates)

        for wc_templates in batches:
            batch_update = {'update': []}
            batch_update_data = []
            for template in wc_templates:
                odoo_template = template.product_tmpl_id
                data = {'id': template.wc_tmpl_id, 'variations': []}
                tmpl_images = []
                position = 0
                gallery_img_keys = {}
                for br_gallery_image in template.wc_gallery_image_ids:
                    res = {}
                    if br_gallery_image.image:
                        key = hashlib.md5(br_gallery_image.image).hexdigest()
                        if not key:
                            continue
                        if key in gallery_img_keys:
                            continue
                        else:
                            gallery_img_keys.update({key: br_gallery_image.id})
                        try:
                            res = img_file_upload.upload_image(wc_instance, br_gallery_image.image, "%s_%s_%s" % (
                                odoo_template.name, odoo_template.categ_id.name, odoo_template.id))
                        except Exception as e:
                            wc_job.env['wc.process.job.cft.line'].create(
                                {'wc_job_id': wc_job.id, 'message': "Error while export images: {0}".format(e)})
                            continue
                    img_url = res and res.get('id', False) or ''
                    if img_url:
                        tmpl_images.append({'id': img_url, 'position': position})
                        position += 1
                else:
                    data.update({"images": False})
                if tmpl_images:
                    data.update({"images": tmpl_images})
                variant_img_keys = {}
                for variant in template.wc_product_ids:
                    if not variant.variant_id or not variant.product_id.attribute_line_ids:
                        continue
                    info = {'id': variant.variant_id}
                    var_url = ''
                    if variant.product_id.image:
                        key = hashlib.md5(variant.product_id.image).hexdigest()
                        if not key in variant_img_keys:
                            try:
                                res = img_file_upload.upload_image(wc_instance, variant.product_id.image,
                                                                   "%s_%s" % (variant.name, variant.id))
                            except Exception as e:
                                wc_job.env['wc.process.job.cft.line'].create(
                                    {'wc_job_id': wc_job.id, 'message': "Error while export images: {0}".format(e)})
                                res = False
                            var_url = res and res.get('id', False) or ''
                            variant_img_keys.update({key: var_url})
                        else:
                            var_url = variant_img_keys.get(key)

                    if var_url:
                        if template.wc_tmpl_id != variant.variant_id and variant.product_id.product_variant_count > 1:
                            info.update({'image': {'id': var_url}})
                            data.get('variations').append(info)
                        elif template.wc_tmpl_id == variant.variant_id and variant.product_id.product_variant_count <= 1:
                            del data['variations']
                            data.update({'images': [{'id': var_url}]})
                if wc_instance.wc_version != 'v1' and data.get('variations'):
                    variant_batches = []
                    start, end = 0, 100
                    if len(data.get('variations')) > 100:
                        while True:
                            w_products_ids = data.get('variations')[start:end]
                            if not w_products_ids:
                                break
                            temp = end + 100
                            start, end = end, temp
                            if w_products_ids:
                                variant_batches.append(w_products_ids)
                    else:
                        variant_batches.append(data.get('variations'))
                    for wc_variants in variant_batches:
                        wcapi.post('products/%s/variations/batch' % (data.get('id')), {'update': wc_variants},
                                   wc_job=wc_job)
                batch_update_data.append(data)
            if batch_update_data:
                batch_update.update({'update': batch_update_data})
                wcapi.post('products/batch', batch_update, wc_job=wc_job)
        return True

    @api.model
    def auto_update_product_stock(self, ctx={}):
        wc_product_tmpl_obj = self.env['wc.product.template.cft']
        wc_instance_obj = self.env['wc.instance.cft']
        if not isinstance(ctx, dict) or not 'wc_instance_id' in ctx:
            return True
        wc_instance_id = ctx.get('wc_instance_id', False)
        wc_instance = wc_instance_id and wc_instance_obj.search(
            [('id', '=', wc_instance_id), ('state', '=', 'confirm')]) or False
        if wc_instance:
            wc_templates = wc_product_tmpl_obj.search(
                [('wc_instance_id', '=', wc_instance_id), ('avail_in_wc', '=', True)])
            self.update_wc_product_stock(wc_instance, wc_templates)
        return True

    @api.model
    def update_wc_product_stock(self, wc_instance=False, wc_products=False):
        wc_job = self.env['wc.process.job.cft'].create(
            {'wc_instance_id': wc_instance.id, 'process_type': 'product', 'operation_type': 'update',
             'message': 'Process for Update Products Stock'})
        instances = []
        if not wc_instance:
            instances = self.env['wc.instance.cft'].search(
                [('stock_auto_export', '=', True), ('state', '=', 'confirm')])
        else:
            instances.append(wc_instance)
        for wc_instance in instances:
            location_ids = wc_instance.warehouse_id.lot_stock_id.child_ids.ids
            location_ids.append(wc_instance.warehouse_id.lot_stock_id.id)
            if not wc_products:
                wc_products = self.search([('wc_instance_id', '=', wc_instance.id), ('avail_in_wc', '=', True)])
            else:
                wc_products = self.search(
                    [('wc_instance_id', '=', wc_instance.id), ('avail_in_wc', '=', True),
                     ('id', 'in', wc_products.ids)])
            if not wc_products:
                continue
            wcapi = wc_instance.wc_connect()
            batches = []
            wc_products_ids = wc_products.ids
            total_wc_products = len(wc_products_ids)
            start, stop = 0, 100
            if total_wc_products > 100:
                while True:
                    w_products_ids = wc_products_ids[start:stop]
                    if not w_products_ids:
                        break
                    temp = stop + 100
                    start, stop = stop, temp
                    if w_products_ids:
                        wc_products = self.browse(w_products_ids)
                        batches.append(wc_products)
            else:
                batches.append(wc_products)
            for wc_products in batches:
                batch_update_data = []
                for template in wc_products:
                    info = {'id': template.wc_tmpl_id, 'variations': []}
                    for variant in template.wc_product_ids:
                        if variant.variant_id and variant.product_id.type == 'product':
                            quantity = self.get_stock(variant, wc_instance.warehouse_id.id,
                                                      wc_instance.stock_field.name)
                            if template.wc_tmpl_id != variant.variant_id and variant.product_id.product_variant_count > 1:
                                info.get('variations').append(
                                    {'id': variant.variant_id, 'manage_stock': True, 'stock_quantity': int(quantity)})
                            elif template.wc_tmpl_id == variant.variant_id and variant.product_id.product_variant_count <= 1:
                                del info['variations']
                                info.update({'manage_stock': True, 'stock_quantity': int(quantity)})
                    if wc_instance.wc_version != 'v1' and info.get('variations'):
                        variant_bathces = []
                        start, stop = 0, 100
                        if len(info.get('variations')) > 100:
                            while True:
                                w_products_ids = info.get('variations')[start:stop]
                                if not w_products_ids:
                                    break
                                temp = stop + 100
                                start, stop = stop, temp
                                if w_products_ids:
                                    variant_bathces.append(w_products_ids)
                        else:
                            variant_bathces.append(info.get('variations'))
                        for wc_variants in variant_bathces:
                            wcapi.post('products/%s/variations/batch' % (info.get('id')),
                                       {'update': wc_variants}, wc_job=wc_job)
                    batch_update_data.append(info)
                if batch_update_data:
                    wcapi.post('products/batch', {'update': batch_update_data}, wc_job=wc_job)
            if not self._context.get('process') == 'update_stock':
                wc_instance.write({'last_inventory_update_time': datetime.now()})
        return True

    @api.model
    def update_wc_product_price(self, wc_instance, wc_templates):
        wc_job = self.env['wc.process.job.cft'].create(
            {'wc_instance_id': wc_instance.id, 'process_type': 'product', 'operation_type': 'update',
             'message': 'Process for Update Products Price'})
        wcapi = wc_instance.wc_connect()
        templates = wc_templates
        batches = []
        wc_templates_ids = templates.ids
        total_wc_templates = len(wc_templates_ids)
        start, stop = 0, 100
        if total_wc_templates > 100:
            while True:
                w_templates_ids = wc_templates_ids[start:stop]
                if not w_templates_ids:
                    break
                temp = stop + 100
                start, stop = stop, temp
                if w_templates_ids:
                    wc_templates = self.browse(w_templates_ids)
                    batches.append(wc_templates)
        else:
            batches.append(templates)
        for wc_templates in batches:
            batch_update = {'update': []}
            batch_update_data = []
            for wc_template in wc_templates:
                info = {'id': wc_template.wc_tmpl_id, 'variations': []}
                for variant in wc_template.wc_product_ids:
                    if variant.variant_id:
                        price = wc_instance.pricelist_id.get_product_price(variant.product_id, 1.0, partner=False,
                                                                           uom_id=variant.product_id.uom_id.id)
                        if wc_template.wc_tmpl_id != variant.variant_id and variant.product_id.product_variant_count > 1:
                            info.get('variations').append(
                                {'id': variant.variant_id, 'regular_price': str(price)})
                        elif wc_template.wc_tmpl_id == variant.variant_id and variant.product_id.product_variant_count <= 1:
                            del info['variations']
                            info.update({'regular_price': str(price)})
                if wc_instance.wc_version != 'v1' and info.get('variations'):
                    variant_batches = []
                    start, stop = 0, 100
                    if len(info.get('variations')) > 100:
                        while True:
                            w_products_ids = info.get('variations')[start:stop]
                            if not w_products_ids:
                                break
                            temp = stop + 100
                            start, stop = stop, temp
                            if w_products_ids:
                                variant_batches.append(w_products_ids)
                    else:
                        variant_batches.append(info.get('variations'))
                    for wc_variants in variant_batches:
                        res = wcapi.post('products/%s/variations/batch' % (info.get('id')), {'update': wc_variants},
                                         wc_job=wc_job)
                        if not res:
                            continue
                batch_update_data.append(info)
            if batch_update_data:
                batch_update.update({'update': batch_update_data})
                res = wcapi.post('products/batch', batch_update, wc_job=wc_job)
                if not res:
                    continue
        return True

    def get_stock(self, wc_product, warehouse_id, stock_type='virtual_available'):
        product = self.env['product.product'].with_context(warehouse=warehouse_id).browse(wc_product.product_id.id)
        if stock_type == 'virtual_available':
            if product.virtual_available > 0.0:
                actual_stock = product.virtual_available - product.incoming_qty
            else:
                actual_stock = 0.0
        else:
            actual_stock = product.qty_available
        if actual_stock >= 1.00:
            if wc_product.fix_stock_type == 'fix':
                if wc_product.fix_stock_value >= actual_stock:
                    return actual_stock
                else:
                    return wc_product.fix_stock_value

            elif wc_product.fix_stock_type == 'percentage':
                quantity = int(actual_stock * wc_product.fix_stock_value)
                if quantity >= actual_stock:
                    return actual_stock
                else:
                    return quantity
        return actual_stock

    @api.model
    def get_product_attribute(self, template, wc_instance, wc_job=False):
        position = 0
        is_variable = False
        attributes = []
        for attribute_line in template.attribute_line_ids:
            options = []
            for option in attribute_line.value_ids:
                options.append(option.name)
            attribute_data = {'name': attribute_line.attribute_id.name,
                              'slug': attribute_line.attribute_id.name.lower(),
                              'position': position,
                              'visible': True,
                              'variation': False if attribute_line.attribute_id.create_variant == 'no_variant' else True,
                              'options': options}
            if wc_instance.attribute_type == 'select':
                attrib_data = self.export_product_attributes_in_wc(wc_instance, attribute_line.attribute_id,
                                                                   wc_job=wc_job)
                if not attrib_data:
                    break
                attribute_data.update({'id': attrib_data.get(attribute_line.attribute_id.id)})
            elif wc_instance.attribute_type == 'text':
                attribute_data.update({'name': attribute_line.attribute_id.name})
            position += 1
            if attribute_line.attribute_id.create_variant:
                is_variable = True
            attributes.append(attribute_data)
        return attributes, is_variable

    @api.model
    def get_variant_image(self, wc_instance, variant, wc_job):
        variant_img_keys = {}
        var_url = ''
        variation_data = {}
        if variant.product_id.image_1920:
            key = hashlib.md5(variant.product_id.image_1920).hexdigest()
            if not key in variant_img_keys:
                try:
                    res = img_file_upload.upload_image(wc_instance, variant.product_id.image_1920,
                                                       "%s_%s" % (variant.name, variant.id))
                except Exception as e:
                    wc_job.env['wc.process.job.cft.line'].create(
                        {'wc_job_id': wc_job.id, 'message': "Error while export images: {0}".format(e)})
                    res = False
                var_url = res and res.get('id', False) or ''
                variant_img_keys.update({key: var_url})
            else:
                var_url = variant_img_keys.get(key)
        if var_url:
            variation_data.update({"image": [{'id': var_url, 'position': 0}]})
        return variation_data

    @api.model
    def get_variant_data(self, variant, wc_instance, update_image, wc_job=False):
        att = []
        wc_attribute_obj = self.env['wc.product.attribute.cft']
        variation_data = {}
        att_data = {}
        for attribute_value in variant.product_id.product_template_attribute_value_ids:
            if wc_instance.attribute_type == 'select':
                wc_attribute = wc_attribute_obj.search(
                    [('name', '=', attribute_value.attribute_id.name), ('wc_instance_id', '=', wc_instance.id),
                     ('avail_in_wc', '=', True)], limit=1)
                att_data = {'id': wc_attribute and wc_attribute.wc_attribute_id, 'option': attribute_value.name}
            if wc_instance.attribute_type == 'text':
                att_data = {'name': attribute_value.attribute_id.name, 'option': attribute_value.name}
            att.append(att_data)
        if update_image:
            variation_data.update(self.get_variant_image(wc_instance, variant, wc_job))
        variation_data.update(
            {'attributes': att, 'sku': str(variant.default_code), 'weight': str(variant.product_id.weight)})
        return variation_data

    @api.model
    def get_product_price(self, wc_instance, variant):
        price = wc_instance.pricelist_id.get_product_price(variant.product_id, 1.0, partner=False,
                                                           uom_id=variant.product_id.uom_id.id)
        return {'regular_price': str(price)}

    @api.model
    def get_product_stock(self, wc_instance, variant):
        quantity = self.get_stock(variant, wc_instance.warehouse_id.id, wc_instance.stock_field.name)
        return {'manage_stock': True, 'stock_quantity': int(quantity)}

    @api.model
    def get_gallery_images(self, wc_instance, wc_template, template, wc_job=False):
        tmpl_images = []
        position = 0
        gallery_img_keys = {}
        for br_gallery_image in wc_template.wc_gallery_image_ids:
            res = {}
            if br_gallery_image.image:
                key = hashlib.md5(br_gallery_image.image).hexdigest()
                if not key:
                    continue
                if key in gallery_img_keys:
                    continue
                else:
                    gallery_img_keys.update({key: br_gallery_image.id})
                try:
                    res = img_file_upload.upload_image(wc_instance, br_gallery_image.image, "%s_%s_%s" % (
                        template.name, template.categ_id.name, template.id))
                except Exception as e:
                    wc_job.env['wc.process.job.cft.line'].create(
                        {'wc_job_id': wc_job.id, 'message': "Error while export images: {0}".format(e)})
                    continue
            img_url = res and res.get('id', False) or ''
            if img_url:
                tmpl_images.append({'id': img_url, 'position': position})
                position += 1
        return tmpl_images

    @api.model
    def update_products(self, wc_instance, templates, update_image):
        wc_job = self.env['wc.process.job.cft'].create(
            {'wc_instance_id': wc_instance.id, 'process_type': 'product', 'operation_type': 'update',
             'message': 'Process for Update Products'})
        wcapi = wc_instance.wc_connect()
        batches = []
        wc_templates_ids = templates.ids
        total_wc_templates = len(wc_templates_ids)

        start, stop = 0, 100
        if total_wc_templates > 100:
            while True:
                w_templates_ids = wc_templates_ids[start:stop]
                if not w_templates_ids:
                    break
                temp = stop + 100
                start, stop = stop, temp
                if w_templates_ids:
                    wc_templates = self.browse(w_templates_ids)
                    batches.append(wc_templates)
        else:
            batches.append(templates)

        for templates in batches:
            batch_update_data = []
            for template in templates:
                categ_ids = []
                tag_ids = []
                data = {'id': template.wc_tmpl_id, 'variations': [], 'name': template.name,
                        'enable_html_description': True,
                        'enable_html_short_description': True, 'description': template.description or '',
                        'short_description': template.short_description or '',
                        'weight': str(template.product_tmpl_id.weight),
                        'taxable': template.taxable and 'true' or 'false'}
                if update_image:
                    tmpl_images = self.get_gallery_images(wc_instance, template, template.product_tmpl_id)
                    data.update({"images": tmpl_images})
                for wc_categ in template.wc_categ_ids:
                    if not wc_categ.wc_categ_id:
                        wc_categ.export_wc_product_category(wc_instance, wc_product_categs=wc_categ,
                                                            export_image=update_image)
                        wc_categ.wc_categ_id and categ_ids.append(wc_categ.wc_categ_id)
                    else:
                        wc_categ.wc_categ_id and categ_ids.append(wc_categ.wc_categ_id)
                categ_ids and data.update({'categories': [{'id': cat_id} for cat_id in categ_ids]})
                for wc_tag in template.wc_tag_ids:
                    if not wc_tag.wc_tag_id:
                        wc_tag.export_product_tags(wc_instance, wc_tag)
                        wc_tag.wc_tag_id and tag_ids.append(wc_tag.wc_tag_id)
                    else:
                        wc_tag.wc_tag_id and tag_ids.append(wc_tag.wc_tag_id)
                    tag_ids and data.update({'tags': [{'id': tag_id} for tag_id in tag_ids]})
                for variant in template.wc_product_ids:
                    if not variant.variant_id:
                        continue
                    info = {}
                    info.update({'id': variant.variant_id, 'weight': str(variant.product_id.weight)})
                    var_url = ''
                    if update_image:
                        info.update(self.get_variant_image(wc_instance, variant, wc_job))
                    if template.wc_tmpl_id != variant.variant_id and variant.product_id.product_template_attribute_value_ids:
                        data.get('variations').append(info)
                    elif template.wc_tmpl_id == variant.variant_id and not variant.product_id.product_template_attribute_value_ids:
                        del data['variations']
                        if var_url:
                            if data.get('images'):
                                data.get('images').insert(0, {'id': var_url, 'position': 0})
                            else:
                                data.update({'images': [{'id': var_url, 'position': 0}]})
                if wc_instance.wc_version != 'v1' and not template.wc_tmpl_id == variant.variant_id:
                    variant_batches = []
                    start, stop = 0, 100
                    if len(data.get('variations')) > 100:
                        while True:
                            w_products_ids = data.get('variations')[start:stop]
                            if not w_products_ids:
                                break
                            temp = stop + 100
                            start, stop = stop, temp
                            if w_products_ids:
                                variant_batches.append(w_products_ids)
                    else:
                        variant_batches.append(data.get('variations'))
                    for wc_variants in variant_batches:
                        wcapi.post('products/%s/variations/batch' % (template.wc_tmpl_id),
                                   {'update': (wc_variants)}, wc_job=wc_job)
                batch_update_data.append(data)
            if batch_update_data:
                wcapi.post('products/batch', {'update': batch_update_data}, wc_job=wc_job)
        return True

    @api.model
    def export_wc_products(self, wc_instance, wc_templates, update_price, update_stock, publish, update_image):
        wc_job = self.env['wc.process.job.cft'].create(
            {'wc_instance_id': wc_instance.id, 'process_type': 'product', 'operation_type': 'export',
             'message': 'Process for Export Products'})
        wcapi = wc_instance.wc_connect()
        wc_product_obj = self.env['wc.product.product.cft']
        wc_product_img = self.env['wc.product.image.cft']
        variants = []

        for wc_template in wc_templates:
            categ_ids = []
            tag_ids = []
            template = wc_template.product_tmpl_id
            data = {'enable_html_description': True, 'enable_html_short_description': True, 'type': 'simple',
                    'name': wc_template.name, 'description': wc_template.description or '',
                    'weight': str(template.weight),
                    'short_description': wc_template.short_description or '',
                    'taxable': wc_template.taxable and 'true' or 'false',
                    'shipping_required': 'true'}
            for wc_categ in wc_template.wc_categ_ids:
                if not wc_categ.wc_categ_id:
                    wc_categ.export_wc_product_category(wc_instance, wc_product_categs=wc_categ,
                                                        export_image=update_image)
                    wc_categ.wc_categ_id and categ_ids.append(wc_categ.wc_categ_id)
                else:
                    wc_categ.wc_categ_id and categ_ids.append(wc_categ.wc_categ_id)
            categ_ids and data.update({'categories': [{'id': cat_id} for cat_id in categ_ids]})
            for wc_tag in wc_template.wc_tag_ids:
                if not wc_tag.wc_tag_id:
                    wc_tag.export_product_tags(wc_instance, wc_tag)
                    wc_tag.wc_tag_id and tag_ids.append(wc_tag.wc_tag_id)
                else:
                    wc_tag.wc_tag_id and tag_ids.append(wc_tag.wc_tag_id)
                tag_ids and data.update({'tags': [{'id': tag_id} for tag_id in tag_ids]})

            if publish:
                data.update({'status': 'publish'})
            else:
                data.update({'status': 'draft'})

            attributes, is_variable = self.get_product_attribute(template, wc_instance, wc_job=wc_job)
            if is_variable:
                data.update({'type': 'variable'})

            if template.attribute_line_ids:
                variations = []
                for variant in wc_template.wc_product_ids:
                    variation_data = {}
                    product_variant = self.get_variant_data(variant, wc_instance, update_image, wc_job=wc_job)
                    variation_data.update(product_variant)
                    if update_price:
                        if data.get('type') == 'simple':
                            data.update(self.get_product_price(wc_instance, variant))
                        else:
                            variation_data.update(self.get_product_price(wc_instance, variant))
                    if update_stock:
                        if data.get('type') == 'simple':
                            data.update(self.get_product_stock(wc_instance, variant))
                        else:
                            variation_data.update(self.get_product_stock(wc_instance, variant))
                    variations.append(variation_data)
                data.update({'attributes': attributes, 'variations': variations})
                if data.get('type') == 'simple':
                    data.update({'sku': str(variant.default_code)})
            else:
                variant = wc_template.wc_product_ids
                data.update(self.get_variant_data(variant, wc_instance, update_image, wc_job=wc_job))
                if update_price:
                    data.update(self.get_product_price(wc_instance, variant))
                if update_stock:
                    data.update(self.get_product_stock(wc_instance, variant))
            if update_image:
                tmpl_images = self.get_gallery_images(wc_instance, wc_template, template, wc_job)
                tmpl_images and data.update({"images": tmpl_images})
            if wc_instance.wc_version != 'v1':
                variants = data.get('variations') or []
                variants and data.update({'variations': []})
            new_product = wcapi.post('products', data, wc_job=wc_job)
            if not new_product:
                continue
            response = new_product.json()
            response_variations = []
            if not wc_instance.wc_version != 'v1':
                response_variations = response.get('variations')
            wc_tmpl_id = response.get('id') or False
            if wc_tmpl_id and wc_instance.wc_version != 'v1' and variants:
                response_variations = []
                variant_batches = []
                start, stop = 0, 100
                if len(variants) > 100:
                    while True:
                        w_products_ids = variants[start:stop]
                        if not w_products_ids:
                            break
                        temp = stop + 100
                        start, stop = stop, temp
                        if w_products_ids:
                            variant_batches.append(w_products_ids)
                else:
                    variant_batches.append(variants)
                for wc_variants in variant_batches:
                    for variant in wc_variants:
                        if variant.get('image'):
                            variant.update({'image': variant.get('image')[0]})
                    variant_response = wcapi.post("products/%s/variations/batch" % (wc_tmpl_id),
                                                  {'create': wc_variants}, wc_job=wc_job)
                    if not variant_response:
                        continue
                    response_variations += variant_response.json().get('create')

            for response_variation in response_variations:
                if response_variation.get('error'):
                    wc_job.env['wc.process.job.cft.line'].create(
                        {'wc_job_id': wc_job.id, 'message': response_variation.get('error')})
                    continue
                response_variant_data = {}
                variant_sku = response_variation.get('sku')
                variant_id = response_variation.get('id')
                variant_created_at = response_variation.get('date_created').replace("T", " ")
                variant_updated_at = response_variation.get('date_modified').replace("T", " ")
                if variant_created_at.startswith('-'):
                    variant_created_at = variant_created_at[1:]
                if variant_updated_at.startswith('-'):
                    variant_updated_at = variant_updated_at[1:]
                wc_product = wc_product_obj.search(
                    [('default_code', '=', variant_sku), ('wc_template_id', '=', wc_template.id),
                     ('wc_instance_id', '=', wc_instance.id)])
                response_variant_data.update(
                    {'variant_id': variant_id, 'created_at': variant_created_at, 'updated_at': variant_updated_at,
                     'avail_in_wc': True})
                wc_product and wc_product.write(response_variant_data)
            tmpl_images = response.get('images')
            offset = 0
            for tmpl_image in tmpl_images:
                tmpl_image_data = {}
                img_id = tmpl_image.get('id')
                position = tmpl_image.get('position')
                if not template.attribute_line_ids and position == 0:
                    continue
                tmpl_image_data.update({'wc_image_id': img_id, 'sequence': position})
                wc_product_tmp_img = wc_product_img.search(
                    [('wc_product_tmpl_id', '=', wc_template.id), ('wc_instance_id', '=', wc_instance.id)],
                    offset=offset, limit=1)
                wc_product_tmp_img and wc_product_tmp_img.write(tmpl_image_data)
                offset += 1
            created_at = response.get('date_created').replace("T", " ")
            updated_at = response.get('date_modified').replace("T", " ")
            if created_at and created_at.startswith('-'):
                created_at = created_at[1:]
            if updated_at and updated_at.startswith('-'):
                updated_at = updated_at[1:]
            if template.product_variant_count == 1:
                wc_product = wc_template.wc_product_ids
                wc_product.write(
                    {'variant_id': wc_tmpl_id, 'created_at': created_at or False, 'updated_at': updated_at or False,
                     'avail_in_wc': True})
            tmpl_data = {'wc_tmpl_id': wc_tmpl_id, 'created_at': created_at or False,
                         'updated_at': updated_at or False, 'avail_in_wc': True,
                         }
            tmpl_data.update({'website_published': True}) if publish else tmpl_data.update({'website_published': False})
            wc_template.write(tmpl_data)
            self._cr.commit()
        return True

    def import_wc_stock(self, wc_instance, wc_products=[]):
        stock_inventory_line_obj = self.env["stock.inventory.line"]
        wc_product_obj = self.env['wc.product.product.cft']
        wc_job = self.env['wc.process.job.cft'].create(
            {'wc_instance_id': wc_instance.id, 'process_type': 'product', 'operation_type': 'import',
             'message': 'Process for Import Product\'s Stock'})
        wcapi = wc_instance.wc_connect()
        wc_invetory = self.env['stock.inventory'].create(
            {'name': 'WCIA/',
             'wc_instance_id': wc_instance.id,
             'location_ids': [(6, 0, [wc_instance.warehouse_id.lot_stock_id.id])]})
        batches = []
        wc_templates_ids = wc_products.ids
        total_wc_templates = len(wc_templates_ids)
        start, stop = 0, 100
        if total_wc_templates > 100:
            while True:
                w_templates_ids = wc_templates_ids[start:stop]
                if not w_templates_ids:
                    break
                temp = stop + 100
                start, stop = stop, temp
                if w_templates_ids:
                    wc_templates = self.browse(w_templates_ids)
                    batches.append(wc_templates)
        else:
            batches.append(wc_products)
        for wc_templates in batches:
            products = []
            tmpl_res = wcapi.get(
                'products?include={0}&per_page=100&_fields=id,variations'.format(
                    ",".join([wcp.wc_tmpl_id for wcp in wc_templates])),
                wc_job=wc_job)
            if not tmpl_res:
                continue
            wc_tmpls = tmpl_res.json()
            if wc_instance.wc_version != 'v1':
                for wc_tmpl in wc_tmpls:
                    variants = []
                    wc_id = wc_tmpl.get('id')
                    variant_response = wcapi.get(
                        'products/%s/variations?per_page=100&_fields=id,stock_quantity,sku' % (wc_id), wc_job=wc_job)
                    if not variant_response:
                        return False
                    variants += variant_response.json()
                    total_pages = variant_response.headers.get('x-wp-totalpages', 0)
                    if int(total_pages) >= 2:
                        for page in range(2, int(total_pages) + 1):
                            page_res = wcapi.get(
                                'products/%s/variations?per_page=100&page=%s&_fields=id,stock_quantity,sku' % (
                                    wc_id, page),
                                wc_job=wc_job)
                            if not page_res:
                                continue
                            variants += page_res.json()
                    products += variants
            else:
                products += tmpl_res.get('variations')
            for product in products:
                wc_product = wc_product_obj.search(
                    [('wc_instance_id', '=', wc_instance.id), ('variant_id', '=', product.get('id'))])
                if not wc_product:
                    continue
                stock_inventory_line = stock_inventory_line_obj.create(
                    {"inventory_id": wc_invetory.id, "product_id": wc_product.product_id.id,
                     "location_id": wc_invetory.location_ids.id, "product_qty": product.get('stock_quantity')})
                # stock_inventory_line.onchange_product()
            if wc_invetory and not wc_invetory.line_ids:
                wc_invetory.unlink()
            else:
                inv_adj_seq = self.env['ir.sequence'].next_by_code('wc.stock.inventory')
                wc_invetory.name = wc_invetory.name + inv_adj_seq
                wc_invetory.action_start()
        return True


class WcProductProduct(models.Model):
    _name = "wc.product.product.cft"
    _order = 'product_id'
    _description = "WooCommerce Product"

    name = fields.Char("Title")
    wc_instance_id = fields.Many2one("wc.instance.cft", "Instance", required=True, ondelete='cascade')
    default_code = fields.Char("Default Code")
    product_id = fields.Many2one("product.product", "Product", required=1)
    wc_template_id = fields.Many2one("wc.product.template.cft", "WooCommerce Template", required=1, ondelete="cascade")
    avail_in_wc = fields.Boolean("Available in WooCommerce")
    variant_id = fields.Char("Variant Id")
    fix_stock_type = fields.Selection([('fix', 'Fix'), ('percentage', 'Percentage')], string='Fix Stock Type')
    fix_stock_value = fields.Float(string='Fix Stock Value', digits="Product UoS")
    created_at = fields.Datetime("Created At")
    updated_at = fields.Datetime("Updated At")
    wc_variant_url = fields.Char(size=600, string='Image URL')
    response_url = fields.Char(size=600, string='Response URL', help="URL from WooCommerce")
    wc_image_id = fields.Char("Image Id", help="WooCommerce Image Id")
