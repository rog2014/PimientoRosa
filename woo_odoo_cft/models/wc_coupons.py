from odoo import models, api, fields
from odoo.exceptions import Warning


class WcCoupons(models.Model):
    _name = "wc.coupons.cft"
    _rec_name = "code"
    _description = "WooCommerce Coupon"

    coupon_id = fields.Integer("WooCommerce Id")
    code = fields.Char("Code", required=1)
    description = fields.Text('Description')
    discount_type = fields.Selection([('fixed_cart', 'Cart Discount'),
                                      ('percent', 'Cart % Discount'),
                                      ('fixed_product', 'Product Discount'),
                                      ('percent_product', 'Product % Discount')
                                      ], "Discount Type", default="fixed_cart")
    amount = fields.Float("Amount")
    free_shipping = fields.Boolean("Allow Free Shipping",
                                   help="Check this box if the coupon grants free shipping. A free shipping method must be enabled in your shipping zone and be set to require \"a valid free shipping coupon\" (see the \"Free Shipping Requires\" setting in WooCommerce).")
    expiry_date = fields.Date("Expiry Date")
    minimum_amount = fields.Float("Minimum Spend")
    maximum_amount = fields.Float("Maximum Spend")
    individual_use = fields.Boolean("Individual Use",
                                    help="Check this box if the coupon cannot be used in conjunction with other coupons.")
    exclude_sale_items = fields.Boolean("Exclude Sale Items",
                                        help="Check this box if the coupon should not apply to items on sale. Per-item coupons will only work if the item is not on sale. Per-cart coupons will only work if there are no sale items in the cart.")
    product_ids = fields.Many2many("wc.product.template.cft", 'wc_product_tmpl_product_rel', 'product_ids',
                                   'wc_product_ids', "Products")
    exclude_product_ids = fields.Many2many("wc.product.template.cft", 'wc_product_tmpl_exclude_product_rel',
                                           'exclude_product_ids', 'wc_product_ids', "Exclude Products")
    product_category_ids = fields.Many2many('wc.category.cft', 'wc_template_categ_incateg_rel',
                                            'product_category_ids', 'wc_categ_id', "Product Categories")
    excluded_product_category_ids = fields.Many2many('wc.category.cft', 'wc_template_categ_exclude_categ_rel',
                                                     'excluded_product_category_ids', 'wc_categ_id',
                                                     "Exclude Product Categories")
    email_restrictions = fields.Char("Email restrictions",
                                     help="List of email addresses that can use this coupon, Enter Email ids Sepreated by comma(,)",
                                     default="")
    usage_limit = fields.Integer("Usage limit per coupon")
    limit_usage_to_x_items = fields.Integer("Limit usage to X items")
    usage_limit_per_user = fields.Integer("Usage limit per user")
    usage_count = fields.Integer("Usage Count")
    date_created = fields.Datetime("Created Date")
    date_modified = fields.Datetime("Modified Date")
    used_by = fields.Char("Used By")
    wc_instance_id = fields.Many2one("wc.instance.cft", "Instance", required=True, ondelete='cascade')
    avail_in_wc = fields.Boolean("Available in WooCommerce")
    _sql_constraints = [('code_unique', 'unique(code,wc_instance_id)', "Code is already exists. Code must be unique!")]

    @api.constrains('product_ids')
    def check_product_ids(self):
        for product in self.product_ids.ids:
            if product in self.exclude_product_ids.ids:
                raise Warning("Same Product is not allow to select in both Products and Exclude Products")

    @api.constrains('product_category_ids')
    def check_product_category_ids(self):
        for category in self.product_category_ids.ids:
            if category in self.excluded_product_category_ids.ids:
                raise Warning("Same Product Category is not allow to select in both Products and Exclude Products")

    @api.constrains('exclude_product_ids')
    def check_exclude_product_ids(self):
        for product in self.exclude_product_ids.ids:
            if product in self.product_ids.ids:
                raise Warning("Same Product is not allow to select in both Products and Exclude Products")

    @api.constrains('excluded_product_category_ids')
    def check_excluded_product_category_ids(self):
        for category in self.excluded_product_category_ids.ids:
            if category in self.product_category_ids.ids:
                raise Warning("Same Product Category is not allow to select in both Products and Exclude Products")

    @api.model
    def export_update_coupons(self, wc_instance, wc_coupons, op_type):
        wcapi = wc_instance.wc_connect()
        if op_type == 'export':
            message = 'Process for Export Coupons'
            type = 'export'
        elif op_type == 'update':
            message = 'Process for Update Coupons'
            type = 'update'
        wc_job = self.env['wc.process.job.cft'].create(
            {'wc_instance_id': wc_instance.id, 'process_type': 'coupon', 'operation_type': type,
             'message': message})
        request_batches = []
        wc_coupon_ids = wc_coupons.ids
        total_wc_coupons = len(wc_coupon_ids)
        start, stop = 0, 100
        if total_wc_coupons > 100:
            while True:
                coupon_ids = wc_coupon_ids[start:stop]
                if not coupon_ids:
                    break
                new_start = stop + 100
                start, stop = stop, new_start
                if coupon_ids:
                    wc_templates = self.browse(coupon_ids)
                    request_batches.append(wc_templates)
        else:
            request_batches.append(wc_coupons)

        for wc_coupons in request_batches:
            batch_update_data = []
            for wc_coupon in wc_coupons:
                wc_product_tmpl_ids = []
                wc_product_exclude_tmpl_ids = []
                wc_category_ids = []
                wc_exclude_category_ids = []
                for product_tmpl_id in wc_coupon.product_ids:
                    wc_product_tmpl_ids.append(product_tmpl_id.wc_tmpl_id)
                for exclude_product_tmpl_id in wc_coupon.exclude_product_ids:
                    wc_product_exclude_tmpl_ids.append(exclude_product_tmpl_id.wc_tmpl_id)
                for categ_id in wc_coupon.product_category_ids:
                    wc_category_ids.append(categ_id.wc_categ_id)
                for exclude_categ_id in wc_coupon.excluded_product_category_ids:
                    wc_exclude_category_ids.append(exclude_categ_id.wc_categ_id)
                email_ids = []
                if wc_coupon.email_restrictions:
                    email_ids = wc_coupon.email_restrictions.split(",")
                row_data = {'code': wc_coupon.code,
                            'description': str(wc_coupon.description or '') or '',
                            'discount_type': wc_coupon.discount_type,
                            'free_shipping': wc_coupon.free_shipping,
                            'amount': str(wc_coupon.amount),
                            'expiry_date' if not wc_instance.wc_version != 'v1' else 'date_expires': str(
                                wc_coupon.expiry_date) or '',
                            'minimum_amount': str(wc_coupon.minimum_amount),
                            'maximum_amount': str(wc_coupon.maximum_amount),
                            'individual_use': wc_coupon.individual_use,
                            'exclude_sale_items': wc_coupon.exclude_sale_items,
                            'product_ids': wc_product_tmpl_ids,
                            'exclude_product_ids' if not wc_instance.wc_version != 'v1' else 'excluded_product_ids': wc_product_exclude_tmpl_ids,
                            'product_categories': wc_category_ids,
                            'excluded_product_categories': wc_exclude_category_ids,
                            'email_restrictions': email_ids,
                            'usage_limit': wc_coupon.usage_limit,
                            'limit_usage_to_x_items': wc_coupon.limit_usage_to_x_items,
                            'usage_limit_per_user': wc_coupon.usage_limit_per_user,
                            }
                if op_type == 'update':
                    row_data.update({'id': wc_coupon.coupon_id})
                batch_update_data.append(row_data)
            if batch_update_data:
                if op_type == 'export':
                    wc_res = wcapi.post("coupons/batch", {'create': batch_update_data}, wc_job=wc_job)
                elif op_type == 'update':
                    wc_res = wcapi.post("coupons/batch", {'update': batch_update_data}, wc_job=wc_job)
                if not wc_res:
                    continue
                wc_coupon_responses = wc_res.json().get('create') if op_type == 'export' else wc_res.json().get(
                    'update')
                for wc_coupon_response in wc_coupon_responses:
                    if wc_coupon_response.get('error'):
                        wc_job.env['wc.process.job.cft.line'].create(
                            {'wc_job_id': wc_job.id, 'message': wc_coupon_response.get('error').get('message')})
                        continue
                    wc_coupon = self.search([('code', '=', wc_coupon_response.get('code'))], limit=1)
                    wc_coupon and wc_coupon.write(
                        {"coupon_id": wc_coupon_response.get("id"), "used_by": wc_coupon_response.get("used_by"),
                         "date_created": wc_coupon_response.get("date_created").replace("T", " "),
                         "date_modified": wc_coupon_response.get("date_modified").replace("T", " "),
                         "avail_in_wc": True})
        return True

    def import_coupons(self, wc_instance):
        wc_product_categ_obj = self.env["wc.category.cft"]
        wc_product_template_obj = self.env["wc.product.template.cft"]
        wcapi = wc_instance.wc_connect()
        wc_job = self.env['wc.process.job.cft'].create(
            {'wc_instance_id': wc_instance.id, 'process_type': 'coupon', 'operation_type': 'import_sync',
             'message': "Process for Import/Sync Coupons"})
        coupon_ids = []
        wc_res = wcapi.get("coupons?per_page=100", wc_job=wc_job)
        if not wc_res:
            return False
        coupon_response = wc_res.json()
        coupon_ids = coupon_ids + coupon_response
        total_pages = wc_res.headers.get('x-wp-totalpages', 0)
        if int(total_pages) >= 2:
            for page in range(2, int(total_pages) + 1):
                wc_res = wcapi.get('coupons?per_page=100&page=%s' % (page), wc_job=wc_job)
                if wc_res:
                    coupon_ids = coupon_ids + wc_res.json()
        for coupon in coupon_ids:
            coupon_id = coupon.get("id")
            code = coupon.get("code")
            free_shipping = coupon.get("free_shipping")
            wc_product_categ = wc_product_categ_obj.search(
                [("wc_categ_id", "in", coupon.get("product_categories")),
                 ("wc_instance_id", "=", wc_instance.id)]).ids
            prodcut_category = [(6, False, wc_product_categ)] or ''
            exclude_wc_product_categ = wc_product_categ_obj.search(
                [("wc_categ_id", "in", coupon.get("excluded_product_categories")),
                 ("wc_instance_id", "=", wc_instance.id)]).ids
            exclude_prodcut_category = [(6, False, exclude_wc_product_categ)] or ''
            email_restriction = coupon.get("email_restrictions") or ''
            discount_type = coupon.get("discount_type")
            wc_coupon = self.search([('code', '=', code), ('wc_instance_id', '=', wc_instance.id)], limit=1)
            wc_product_ids = wc_product_template_obj.search(
                [("wc_tmpl_id", "in", coupon.get("product_ids")), ("wc_instance_id", "=", wc_instance.id)]).ids
            if not wc_instance.wc_version != 'v1':
                exclude_wc_product_ids = wc_product_template_obj.search(
                    [("wc_tmpl_id", "in", coupon.get("exclude_product_ids")),
                     ("wc_instance_id", "=", wc_instance.id)]).ids
                expiry_date = coupon.get("expiry_date") and coupon.get("expiry_date").replace("T", " ") or False
            else:
                exclude_wc_product_ids = wc_product_template_obj.search(
                    [("wc_tmpl_id", "in", coupon.get("excluded_product_ids")),
                     ("wc_instance_id", "=", wc_instance.id)]).ids
                expiry_date = coupon.get("date_expires") and coupon.get("date_expires").replace("T", " ") or False
            email_ids = ""
            if email_restriction:
                email_ids = ",".join(email_restriction)
            vals = {
                'coupon_id': coupon_id,
                'code': code,
                'description': coupon.get("description"),
                'amount': coupon.get("amount"),
                'free_shipping': free_shipping,
                'expiry_date': expiry_date,
                'minimum_amount': coupon.get("minimum_amount"),
                'maximum_amount': coupon.get("minimum_amount"),
                'individual_use': coupon.get("individual_use"),
                'exclude_sale_items': coupon.get("exclude_sale_items"),
                'discount_type': discount_type,
                'product_ids': [(6, False, wc_product_ids)] or '',
                'exclude_product_ids': [(6, False, exclude_wc_product_ids)] or '',
                'product_category_ids': prodcut_category or '',
                'excluded_product_category_ids': exclude_prodcut_category or '',
                'limit_usage_to_x_items': coupon.get("limit_usage_to_x_items"),
                'usage_limit_per_user': coupon.get("usage_limit_per_user"),
                'usage_count': coupon.get("usage_count"),
                'date_created': coupon.get("date_created").replace("T", " "),
                'date_modified': coupon.get("date_modified").replace("T", " "),
                'email_restrictions': email_ids,
                'usage_limit': coupon.get("usage_limit"),
                'used_by': coupon.get("used_by"),
                'wc_instance_id': wc_instance.id,
                'avail_in_wc': True
            }
            if not wc_coupon:
                self.create(vals)
            else:
                wc_coupon.write(vals)
        return True
