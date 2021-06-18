from odoo import models, fields, api, _
from ..wc_api import img_file_upload
import base64
import requests
from odoo.exceptions import ValidationError


class WcProductCategory(models.Model):
    _name = 'wc.category.cft'
    _order = 'wc_categ_id'
    _description = "WooCommerce Product Category"
    _parent_name = "parent_id"
    _parent_store = True
    _parent_order = 'name'
    _rec_name = 'complete_name'

    @api.constrains('parent_id')
    def _check_category_recursion(self):
        if not self._check_recursion():
            raise ValidationError(_('Error ! You cannot create recursive categories.'))
        return True

    name = fields.Char('Name', required="1", translate=True)
    parent_id = fields.Many2one('wc.category.cft', string='Parent', index=True, ondelete='cascade')
    description = fields.Char('Description', translate=True)
    slug = fields.Char(string='Slug',
                       help="An alphanumeric identifier for the resource unique to its type.")
    display = fields.Selection([('default', 'Default'),
                                ('products', 'Products'),
                                ('subcategories', 'Sub Categories'),
                                ('both', 'Both')
                                ], default='default')
    image = fields.Binary('Image')
    wc_categ_id = fields.Integer('WooCommerce Category Id', readonly=True)
    parent_left = fields.Integer('Left Parent', index=1)
    parent_right = fields.Integer('Right Parent', index=1)
    wc_instance_id = fields.Many2one("wc.instance.cft", "Instance", required=True, ondelete='cascade')
    avail_in_wc = fields.Boolean('Available in WooCommerce', default=False, readonly=True)
    complete_name = fields.Char('Complete Name', compute='_compute_complete_name')
    parent_path = fields.Char(index=True)

    @api.depends('name', 'parent_id.complete_name')
    def _compute_complete_name(self):
        for category in self:
            if category.parent_id:
                category.complete_name = '%s / %s' % (category.parent_id.complete_name, category.name)
            else:
                category.complete_name = category.name

    @api.model
    def name_create(self, name):
        return self.create({'name': name}).name_get()[0]

    def export_wc_product_category(self, wc_instance, wc_product_categs, export_image=False):
        wc_job = self.env['wc.process.job.cft'].create(
            {'wc_instance_id': wc_instance.id, 'process_type': 'category', 'operation_type': 'export',
             'message': 'Process for Export Product Category'})
        wcapi = wc_instance.wc_connect()
        for wc_product_categ in wc_product_categs:
            product_categs = []
            product_categs.append(wc_product_categ)
            for categ in product_categs:
                if categ.parent_id and categ.parent_id not in product_categs and not categ.parent_id.wc_categ_id:
                    product_categs.append(categ.parent_id)

            product_categs.reverse()
            for wc_product_categ in product_categs:
                res = {}
                if wc_product_categ.image and export_image:
                    try:
                        res = img_file_upload.upload_image(wc_instance, wc_product_categ.image,
                                                           "%s_%s" % (wc_product_categ.name, wc_product_categ.id))
                    except Exception as e:
                        wc_job.env['wc.process.job.cft.line'].create(
                            {'wc_job_id': wc_job.id, 'message': "Error while export images: {0}".format(e)})
                img_url = res and res.get('url', False) or ''
                row_data = {'name': str(wc_product_categ.name),
                            'description': str(wc_product_categ.description or ''),
                            'display': str(wc_product_categ.display),
                            }
                if wc_product_categ.slug:
                    row_data.update({'slug': str(wc_product_categ.slug)})
                img_url and row_data.update({'image': img_url})
                wc_product_categ.parent_id.wc_categ_id and row_data.update(
                    {'parent': wc_product_categ.parent_id.wc_categ_id})
                res = wcapi.post("products/categories", row_data, wc_job=wc_job)
                if not hasattr(res, 'status_code') and not res:
                    return False
                product_categ = res.json()
                response_data = {}
                if product_categ.get('code') == 'term_exists':
                    product_categ_id = product_categ.get('data').get('resource_id')
                else:
                    product_categ_id = product_categ and product_categ.get('id', False)
                    slug = product_categ and product_categ.get('slug', '')
                    response_data.update({'slug': slug})
                if product_categ_id:
                    response_data.update({'wc_categ_id': product_categ_id, 'avail_in_wc': True})
                    wc_product_categ.write(response_data)
        return True

    def update_product_categs(self, wc_instance, wc_product_categs, export_image=False):
        wc_job = self.env['wc.process.job.cft'].create(
            {'wc_instance_id': wc_instance.id, 'process_type': 'category', 'operation_type': 'update',
             'message': 'Process for Update Product Category'})
        wcapi = wc_instance.wc_connect()
        updated_categs = []
        for wc_categ in wc_product_categs:
            if wc_categ in updated_categs:
                continue
            product_categs = []
            product_categs.append(wc_categ)
            for categ in product_categs:
                if categ.parent_id and categ.parent_id not in product_categs and categ.parent_id not in updated_categs:
                    self.sync_product_category(wc_instance, wc_product_categ=categ.parent_id)
                    product_categs.append(categ.parent_id)

            product_categs.reverse()
            for wc_categ in product_categs:
                res = {}
                if wc_categ.image and export_image:
                    try:
                        res = img_file_upload.upload_image(wc_instance, wc_categ.image,
                                                           "%s_%s" % (wc_categ.name, wc_categ.id))
                    except Exception as e:
                        wc_job.env['wc.process.job.cft.line'].create(
                            {'wc_job_id': wc_job.id, 'message': "Error while export images: {0}".format(e)})
                img_url = res and res.get('url', False) or ''

                row_data = {'name': str(wc_categ.name),
                            'display': str(wc_categ.display),
                            'description': str(wc_categ.description or '')}
                if wc_categ.slug:
                    row_data.update({'slug': str(wc_categ.slug)})
                row_data.update({'image': {'src': img_url}})
                wc_categ.parent_id.wc_categ_id and row_data.update({'parent': wc_categ.parent_id.wc_categ_id})
                row_data.update({'id': wc_categ.wc_categ_id})
                if wcapi.post('products/categories/batch', {'update': [row_data]}, wc_job=wc_job):
                    updated_categs.append(wc_categ)
        return True

    def sync_product_category(self, wc_instance, wc_categ=False, sync_images_with_product=False):
        wc_job = self.env['wc.process.job.cft'].create(
            {'wc_instance_id': wc_instance.id, 'process_type': 'category', 'operation_type': 'import_sync',
             'message': 'Process for Import/Sync Product Category'})
        wcapi = wc_instance.wc_connect()
        if wc_categ:
            response = wcapi.get("products/categories?per_page=100&include={0}".format([wc_categ]), wc_job=wc_job)
        else:
            response = wcapi.get("products/categories?per_page=100", wc_job=wc_job)
        total_pages = response and response.headers.get('x-wp-totalpages') or 1
        results = response.json()
        if int(total_pages) >= 2:
            for page in range(2, int(total_pages) + 1):
                wc_res = wcapi.get("products/categories?per_page=100&page=%s" % (page), wc_job=wc_job)
                if wc_res:
                    results += wc_res.json()
        categs = {}
        processed_categs = []
        for result in results:
            if result.get('id') in processed_categs:
                continue
            if result.get('parent'):
                categs.update({result.get('id'): result})
            else:
                self.create_update_wc_categ(result, wc_instance, sync_images_with_product)
                processed_categs.append(result.get('id', False))
        while categs:
            for result in list(categs.keys()):
                result = categs.get(result)
                if result.get('id') in processed_categs:
                    continue
                parent_wc_id = result.get('parent')
                parent_id = self.search([('wc_categ_id', '=', parent_wc_id), ('wc_instance_id', '=', wc_instance.id)],
                                        limit=1)
                if parent_id:
                    self.create_update_wc_categ(result, wc_instance, sync_images_with_product)
                    processed_categs.append(result.get('id', False))
                    del categs[result.get('id')]
        return True

    def create_update_wc_categ(self, result, wc_instance, sync_images_with_product):
        if not result:
            return False
        wc_categ_id = result.get('id')
        wc_categ_name = result.get('name')
        display = result.get('display')
        slug = result.get('slug')
        parent_wc_id = result.get('parent')
        parent_id = False
        binary_img_data = False
        if parent_wc_id:
            parent_id = self.search(
                [('wc_categ_id', '=', parent_wc_id), ('wc_instance_id', '=', wc_instance.id)], limit=1).id
        vals = {'name': wc_categ_name, 'wc_instance_id': wc_instance.id, 'display': display, 'slug': slug,
                'avail_in_wc': True, 'parent_id': parent_id, 'description': result.get('description', '')}
        if sync_images_with_product:
            res_image = result.get('image') and result.get('image').get('src', '')
            if res_image:
                try:
                    res_img = requests.get(res_image, stream=True, verify=False, timeout=10)
                    if res_img.status_code == 200:
                        binary_img_data = base64.b64encode(res_img.content)
                except Exception:
                    pass
            binary_img_data and vals.update({'image': binary_img_data})
        vals.update({'wc_categ_id': wc_categ_id, 'slug': slug})
        wc_product_categ = self.search(
            [('wc_categ_id', '=', wc_categ_id), ('wc_instance_id', '=', wc_instance.id)])
        if not wc_product_categ:
            wc_product_categ = self.search([('slug', '=', slug), ('wc_instance_id', '=', wc_instance.id)],
                                           limit=1)
        if wc_product_categ:
            wc_product_categ.write(vals)
        else:
            self.create(vals)
        return True
