from odoo import models, fields, api


class WcTags(models.Model):
    _name = "wc.tags.cft"
    _order = 'name'
    _description = "WooCommerce Product Tag"

    name = fields.Char("Name", required=1)
    description = fields.Text('Description')
    slug = fields.Char(string='Slug',
                       help="The slug is the URL-friendly version of the name. It is usually all lowercase and contains only letters, numbers, and hyphens.")
    wc_tag_id = fields.Integer("WooCommerce Tag Id")
    avail_in_wc = fields.Boolean("Available in WooCommerce", default=False)
    wc_instance_id = fields.Many2one("wc.instance.cft", "Instance", required=True, ondelete='cascade')

    @api.model
    def export_product_tags(self, wc_instance, wc_product_tags):
        wc_job = self.env['wc.process.job.cft'].create(
            {'wc_instance_id': wc_instance.id, 'process_type': 'tag', 'operation_type': 'export',
             'message': 'Process for Export Product Tags'})
        wcapi = wc_instance.wc_connect()
        request_batches = []
        wc_tags_ids = wc_product_tags.ids
        total_wc_tags = len(wc_tags_ids)
        start, stop = 0, 100
        if total_wc_tags > 100:
            while True:
                tags_ids = wc_tags_ids[start:stop]
                if not tags_ids:
                    break
                new_start = stop + 100
                start, stop = stop, new_start
                tags_ids and request_batches.append(self.browse(tags_ids))
        else:
            request_batches.append(wc_product_tags)

        for wc_tmpl_tags in request_batches:
            batch_update_data = []
            for wc_product_tag in wc_tmpl_tags:
                row_data = {'name': wc_product_tag.name, 'description': str(wc_product_tag.description or '')}
                wc_product_tag.slug and row_data.update({'slug': str(wc_product_tag.slug)})
                batch_update_data.append(row_data)
            if not batch_update_data:
                continue
            res = wcapi.post("products/tags/batch", {"create": batch_update_data}, wc_job=wc_job)
            for product_tag in res.json().get('create'):
                if product_tag.get('error') and not product_tag.get('error').get('code'):
                    wc_job.env['wc.process.job.cft.line'].create(
                        {'wc_job_id': wc_job.id, 'message': product_tag.get('error').get('message')})
                    continue
                update_vals = {}
                if product_tag.get('error').get('code') == 'term_exists':
                    product_tag_id = product_tag.get('error').get('data').get('resource_id')
                else:
                    product_tag_id = product_tag and product_tag.get('id', False)
                    slug = product_tag and product_tag.get('slug', '')
                    update_vals.update({'slug': slug})
                if product_tag_id:
                    update_vals.update({'wc_tag_id': product_tag_id, 'avail_in_wc': True})
                    wc_product_tag.write(update_vals)
        return True

    @api.model
    def update_product_tags(self, wc_instance, wc_product_tags):
        wc_job = self.env['wc.process.job.cft'].create(
            {'wc_instance_id': wc_instance.id, 'process_type': 'tag', 'operation_type': 'update',
             'message': 'Process for Update Product Tags'})
        wcapi = wc_instance.wc_connect()
        request_batches = []
        wc_tags_ids = wc_product_tags.ids
        total_wc_tags = len(wc_tags_ids)
        start, stop = 0, 100
        if total_wc_tags > 100:
            while True:
                tags_ids = wc_tags_ids[start:stop]
                if not tags_ids:
                    break
                new_start = stop + 100
                start, stop = stop, new_start
                tags_ids and request_batches.append(self.browse(tags_ids))
        else:
            request_batches.append(wc_product_tags)
        for wc_tmpl_tags in request_batches:
            batch_update_data = []
            for wc_product_tag in wc_tmpl_tags:
                row_data = {'name': wc_product_tag.name, 'description': str(wc_product_tag.description or '')}
                wc_product_tag.slug and row_data.update({'slug': str(wc_product_tag.slug)})
                batch_update_data.append(row_data)
            if not batch_update_data:
                continue
            wcapi.post("products/tags/batch", {"update": batch_update_data}, wc_job=wc_job)
        return True

    def sync_product_tags(self, wc_instance, wc_product_tag=False):
        wc_job = self.env['wc.process.job.cft'].create(
            {'wc_instance_id': wc_instance.id, 'process_type': 'tag', 'operation_type': 'import_sync',
             'message': 'Process for Import/Sync Product Tags'})
        wcapi = wc_instance.wc_connect()
        res = wcapi.get("products/tags?per_page=100", wc_job=wc_job)
        if not res:
            return False
        total_pages = res and res.headers.get('x-wp-totalpages', 0) or 1
        results = res.json()
        if int(total_pages) >= 2:
            for page in range(2, int(total_pages) + 1):
                wc_res = wcapi.get("products/tags?per_page=100&page=%s" % (page), wc_job=wc_job)
                if wc_res:
                    results += wc_res.json()
        for res in results:
            tag_id = res.get('id')
            name = res.get('name')
            description = res.get('description')
            slug = res.get('slug')
            wc_tag = self.search([('wc_tag_id', '=', tag_id), ('wc_instance_id', '=', wc_instance.id)], limit=1)
            if not wc_tag:
                wc_tag = self.search([('slug', '=', slug), ('wc_instance_id', '=', wc_instance.id)], limit=1)
            if wc_tag:
                wc_tag.write({'wc_tag_id': tag_id, 'name': name, 'description': description,
                              'slug': slug, 'avail_in_wc': True})
            else:
                self.create({'wc_tag_id': tag_id, 'name': name, 'description': description,
                             'slug': slug, 'wc_instance_id': wc_instance.id, 'avail_in_wc': True})
        return True
