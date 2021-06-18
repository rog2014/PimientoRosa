from odoo import models, fields, api, _
from odoo.exceptions import Warning
from .. import wc_api
import requests
from datetime import datetime
from dateutil.relativedelta import relativedelta
import json

_intervalTypes = {
    'work_days': lambda interval: relativedelta(days=interval),
    'days': lambda interval: relativedelta(days=interval),
    'hours': lambda interval: relativedelta(hours=interval),
    'weeks': lambda interval: relativedelta(days=7 * interval),
    'months': lambda interval: relativedelta(months=interval),
    'minutes': lambda interval: relativedelta(minutes=interval),
}

TYPE2JOURNAL = {
    'out_invoice': 'sale',
    'in_invoice': 'purchase',
    'out_refund': 'sale_refund',
    'in_refund': 'purchase_refund',
}


class WcInstance(models.Model):
    _name = "wc.instance.cft"
    _description = "WooCommerce Instance"

    @api.model
    def stock_field_default_value(self):
        qty_available = self.env['ir.model.fields'].search(
            [('model_id.model', '=', 'product.product'), ('name', '=', 'qty_available')], limit=1)
        return qty_available and qty_available.id

    @api.model
    def journal_default_value(self):
        inv_type = self._context.get('move_type', 'out_invoice')
        inv_types = inv_type if isinstance(inv_type, list) else [inv_type]
        company_id = self._context.get('company_id', self.env.user.company_id.id)
        domain = [
            ('type', 'in', list(filter(None, list(map(TYPE2JOURNAL.get, inv_types))))),
            ('company_id', '=', company_id),
        ]
        return self.env['account.journal'].search(domain, limit=1)

    def compute_instance_details(self):
        for instance in self:
            instance.order_count = len(self.env['sale.order'].search([('wc_instance_id', '=', instance.id)]))
            instance.product_count = len(
                self.env['wc.product.template.cft'].search([('wc_instance_id', '=', instance.id)]))
            instance.invoice_count = len(self.env['account.move'].search([('wc_instance_id', '=', instance.id)]))
            instance.delivery_count = len(self.env['stock.picking'].search([('wc_instance_id', '=', instance.id)]))
            instance.categs_count = len(self.env['wc.category.cft'].search([('wc_instance_id', '=', instance.id)]))
            instance.tags_count = len(self.env['wc.tags.cft'].search([('wc_instance_id', '=', instance.id)]))
            instance.customer_count = len(self.env['res.partner'].search(
                [('is_wc_customer', '=', True), ('customer_rank', '>', 0), ('parent_id', '=', False),
                 ('wc_instance_id', '=', instance.id)]))
            instance.coupon_count = len(self.env['wc.coupons.cft'].search([('wc_instance_id', '=', instance.id)]))

    name = fields.Char('Name', required=True)
    company_id = fields.Many2one('res.company', 'Company', required=True,
                                 default=lambda self: self.env.user.company_id.id)
    warehouse_id = fields.Many2one('stock.warehouse', 'Warehouse')
    pricelist_id = fields.Many2one('product.pricelist', 'Pricelist')
    lang_id = fields.Many2one('res.lang', 'Language')
    wc_order_prefix = fields.Char('Order Prefix')
    import_order_status_ids = fields.Many2many('wc.order.status.cft', string="Import Order Status",
                                               help="Selected status orders will be imported from WooCommerce")
    import_order_after = fields.Datetime("Import Order After")
    stock_auto_export = fields.Boolean("Stock Auto Export?")
    fiscal_position_id = fields.Many2one('account.fiscal.position', 'Fiscal Position')
    stock_field = fields.Many2one('ir.model.fields', 'Stock Field', default=stock_field_default_value)
    website_url = fields.Char("WooCommerce Store URL", required=True)
    auto_create_product = fields.Boolean("Auto Create Product?",
                                         help="Check if you want to create automatically product when import it from WooCommerce and not available in Odoo.")
    consumer_key = fields.Char("Consumer Key", required=True,
                               help="Login into WooCommerce site,Go to Dashboard > WooCommerce > Settings > API > Keys/Apps > Click on Add Key")
    consumer_secret = fields.Char("Consumer Secret", required=True,
                                  help="Login into WooCommerce site,Go to Dashboard > WooCommerce > Settings > API > Keys/Apps > Click on Add Key")
    verify_ssl = fields.Boolean("Verify SSL", default=False,
                                help="Check this if your WooCommerce site is using SSL certificate")
    team_id = fields.Many2one('crm.team', 'Sales Team')
    payment_term_id = fields.Many2one('account.payment.term', 'Payment Term')
    discount_line_product_id = fields.Many2one("product.product", "Discount Product", domain=[('type', '=', 'service')])
    fee_line_product_id = fields.Many2one("product.product", "Fees Product", domain=[('type', '=', 'service')])
    last_inventory_update_time = fields.Datetime("Last Inventory Update Time")
    state = fields.Selection([('draft', 'Draft'), ('connect', 'Connected'), ('confirm', 'Confirmed')],
                             default='draft')
    wc_username = fields.Char("Username", help="WooCommerce UserName,Used to Export Image Files.")
    wc_password = fields.Char("Password", help="WooCommerce Password,Used to Export Image Files.")
    wc_version = fields.Selection([('v1', '2.6.x or later'), ('v2', '3.0.x or later'), ('v3', '3.5.x or later')],
                                  "WooCommerce Version", default='v2',
                                  help="Set the appropriate WooCommerce Version you are using currently or\nLogin into WooCommerce site,Go to Dashboard > Plugins")
    is_set_price = fields.Boolean("Set Price ?", default=False)
    is_set_stock = fields.Boolean("Set Stock ?", default=False)
    is_publish = fields.Boolean("Publish In Website ?", default=False)
    is_set_image = fields.Boolean("Set Image ?", default=False)
    sync_images_with_product = fields.Boolean("Sync Images?",
                                              help="Check if you want to import images along with products",
                                              default=False)
    sync_price_with_product = fields.Boolean("Sync Product Price?",
                                             help="Check if you want to import price along with products",
                                             default=False)
    attribute_type = fields.Selection([('select', 'Select'), ('text', 'Text')], 'Attribute Type', default='text')
    color = fields.Integer('Color Index')
    journal_id = fields.Many2one('account.journal', 'Payment Journal', domain=[('type', 'in', ['cash', 'bank'])])
    sale_journal_id = fields.Many2one('account.journal', 'Sales Journal', default=journal_default_value,
                                      domain=[('type', '=', 'sale')])
    picking_policy = fields.Selection(
        [('direct', 'Deliver each product when available'), ('one', 'Deliver all products at once')],
        'Shipping Policy')
    invoice_policy = fields.Selection([('order', 'Ordered quantities'), ('delivery', 'Delivered quantities'), ],
                                      'Invoicing Policy')
    so_auto_import = fields.Boolean('Auto Import Sale Order?')
    so_import_cron_id = fields.Many2one('ir.cron')
    so_import_interval_number = fields.Integer('Import Sale Order Interval Number', help="Repeat every x.", default=10)
    so_import_interval_type = fields.Selection([('minutes', 'Minutes'),
                                                ('hours', 'Hours'), ('work_days', 'Work Days'), ('days', 'Days'),
                                                ('weeks', 'Weeks'), ('months', 'Months')],
                                               'Import Sale Order Interval Unit')
    so_import_next_execution = fields.Datetime('Next Execution', help='Next execution time')
    so_import_user_id = fields.Many2one('res.users', string="User", help='User', default=lambda self: self.env.user)
    so_auto_update = fields.Boolean("Auto Update Sale Order?",
                                    help="Will automatically update order details to the WooCommerce.")
    so_update_cron_id = fields.Many2one('ir.cron')
    so_update_interval_number = fields.Integer('Update Sale Order Interval Number', help="Repeat every x.", default=10)
    so_update_interval_type = fields.Selection([('minutes', 'Minutes'),
                                                ('hours', 'Hours'), ('work_days', 'Work Days'), ('days', 'Days'),
                                                ('weeks', 'Weeks'), ('months', 'Months')],
                                               'Update Sale Order Interval Unit')
    so_update_next_execution = fields.Datetime('Next Execution', help='Next execution time')
    so_update_user_id = fields.Many2one('res.users', string="User", help='User', default=lambda self: self.env.user)

    stock_auto_update = fields.Boolean("Auto Update Product Stock?",
                                       help="Will automatically update product stock details to the WooCommerce.")
    stock_update_cron_id = fields.Many2one('ir.cron')
    stock_update_interval_number = fields.Integer('Update Product Stock Interval Number', help="Repeat every x.",
                                                  default=10)
    stock_update_interval_type = fields.Selection([('minutes', 'Minutes'),
                                                   ('hours', 'Hours'), ('work_days', 'Work Days'), ('days', 'Days'),
                                                   ('weeks', 'Weeks'), ('months', 'Months')],
                                                  'Update Product Stock Interval Unit')
    stock_update_next_execution = fields.Datetime('Next Execution', help='Next execution time')
    stock_update_user_id = fields.Many2one('res.users', string="User", help='User', default=lambda self: self.env.user)
    order_count = fields.Integer(compute=compute_instance_details)
    product_count = fields.Integer(compute=compute_instance_details)
    invoice_count = fields.Integer(compute=compute_instance_details)
    delivery_count = fields.Integer(compute=compute_instance_details)
    categs_count = fields.Integer(compute=compute_instance_details)
    tags_count = fields.Integer(compute=compute_instance_details)
    customer_count = fields.Integer(compute=compute_instance_details)
    coupon_count = fields.Integer(compute=compute_instance_details)

    def button_reset(self):
        self.write({'state': 'draft'})
        return True

    @api.model
    def create(self, vals):
        res = super(WcInstance, self).create(vals)
        if 'so_auto_import' in vals:
            res.setup_import_so_cron()
        if 'so_auto_update' in vals:
            res.setup_update_so_cron()
        if 'stock_auto_update' in vals:
            res.setup_update_stock_cron()
        return res

    def write(self, vals):
        res = super(WcInstance, self).write(vals)
        for instance in self:
            if 'so_auto_import' in vals:
                instance.setup_import_so_cron()
            if 'so_auto_update' in vals:
                instance.setup_update_so_cron()
            if 'stock_auto_update' in vals:
                instance.setup_update_stock_cron()
        return res

    def setup_import_so_cron(self):
        if self.so_auto_import:
            try:
                cron_available = self.env.ref('woo_odoo_cft.ir_cron_import_wc_orders_%d' % (self.id),
                                              raise_if_not_found=False)
            except:
                cron_available = False
            nextcall = datetime.now()
            nextcall += _intervalTypes[self.so_import_interval_type](self.so_import_interval_number)
            vals = {
                'active': True,
                'interval_number': self.so_import_interval_number,
                'interval_type': self.so_import_interval_type,
                'nextcall': nextcall.strftime('%Y-%m-%d %H:%M:%S'),
                'code': "model.auto_import_wc_sale_order(ctx={'wc_instance_id':%d})" % (self.id),
                'user_id': self.so_import_user_id and self.so_import_user_id.id}

            if cron_available:
                vals.update({'name': cron_available.name})
                cron_available.write(vals)
            else:
                try:
                    import_wc_so_cron = self.env.ref('woo_odoo_cft.ir_cron_import_wc_orders')
                except:
                    import_wc_so_cron = False
                if not import_wc_so_cron:
                    raise Warning(
                        'Please upgrade WooCommerce Connector module.')

                name = self.name + ' : ' + import_wc_so_cron.name
                vals.update({'name': name})
                new_cron = import_wc_so_cron.copy(default=vals)
                import_so_cron = self.env['ir.model.data'].create({'module': 'woo_odoo_cft',
                                                                   'name': 'ir_cron_import_wc_orders_%d' % (self.id),
                                                                   'model': 'ir.cron',
                                                                   'res_id': new_cron.id,
                                                                   'noupdate': True
                                                                   })
                import_so_cron and self.update({'so_import_cron_id': new_cron.id})
        else:
            try:
                cron_available = self.env.ref('woo_odoo_cft.ir_cron_import_wc_orders_%d' % (self.id))
            except:
                cron_available = False

            if cron_available:
                cron_available.write({'active': False})
        return True

    def setup_update_so_cron(self):
        if self.so_auto_update:
            try:
                cron_available = self.env.ref('woo_odoo_cft.ir_cron_update_wc_orders_%d' % (self.id),
                                              raise_if_not_found=False)
            except:
                cron_available = False
            nextcall = datetime.now()
            nextcall += _intervalTypes[self.so_update_interval_type](self.so_update_interval_number)
            vals = {
                'active': True,
                'interval_number': self.so_update_interval_number,
                'interval_type': self.so_update_interval_type,
                'nextcall': nextcall.strftime('%Y-%m-%d %H:%M:%S'),
                'code': "model.auto_update_wc_order_status(ctx={'wc_instance_id':%d})" % (self.id),
                'user_id': self.so_update_user_id and self.so_update_user_id.id}

            if cron_available:
                vals.update({'name': cron_available.name})
                cron_available.write(vals)
            else:
                try:
                    update_wc_so_cron = self.env.ref('woo_odoo_cft.ir_cron_update_wc_orders')
                except:
                    update_wc_so_cron = False
                if not update_wc_so_cron:
                    raise Warning(
                        'Please upgrade WooCommerce Connector module.')

                name = self.name + ' : ' + update_wc_so_cron.name
                vals.update({'name': name})
                new_cron = update_wc_so_cron.copy(default=vals)
                update_so_cron = self.env['ir.model.data'].create({'module': 'woo_odoo_cft',
                                                                   'name': 'ir_cron_update_wc_orders_%d' % (self.id),
                                                                   'model': 'ir.cron',
                                                                   'res_id': new_cron.id,
                                                                   'noupdate': True
                                                                   })
                update_so_cron and self.update({'so_update_cron_id': new_cron.id})
        else:
            try:
                cron_available = self.env.ref('woo_odoo_cft.ir_cron_update_wc_orders_%d' % (self.id))
            except:
                cron_available = False

            if cron_available:
                cron_available.write({'active': False})
        return True

    def setup_update_stock_cron(self):
        if self.stock_auto_update:
            try:
                cron_available = self.env.ref('woo_odoo_cft.ir_cron_update_wc_product_stock_%d' % (self.id),
                                              raise_if_not_found=False)
            except:
                cron_available = False
            nextcall = datetime.now()
            nextcall += _intervalTypes[self.stock_update_interval_type](self.stock_update_interval_number)
            vals = {
                'active': True,
                'interval_number': self.stock_update_interval_number,
                'interval_type': self.stock_update_interval_type,
                'nextcall': nextcall.strftime('%Y-%m-%d %H:%M:%S'),
                'code': "model.auto_update_product_stock(ctx={'wc_instance_id':%d})" % (self.id),
                'user_id': self.stock_update_user_id and self.stock_update_user_id.id}

            if cron_available:
                vals.update({'name': cron_available.name})
                cron_available.write(vals)
            else:
                try:
                    update_wc_stock_cron = self.env.ref('woo_odoo_cft.ir_cron_update_wc_product_stock')
                except:
                    update_wc_stock_cron = False
                if not update_wc_stock_cron:
                    raise Warning(
                        'Please upgrade WooCommerce Connector module.')

                name = self.name + ' : ' + update_wc_stock_cron.name
                vals.update({'name': name})
                new_cron = update_wc_stock_cron.copy(default=vals)
                update_stock_cron = self.env['ir.model.data'].create({'module': 'woo_odoo_cft',
                                                                      'name': 'ir_cron_update_wc_product_stock_%d' % (
                                                                          self.id),
                                                                      'model': 'ir.cron',
                                                                      'res_id': new_cron.id,
                                                                      'noupdate': True
                                                                      })
                update_stock_cron and self.update({'stock_update_cron_id': new_cron.id})
        else:
            try:
                cron_available = self.env.ref('woo_odoo_cft.ir_cron_update_wc_product_stock_%d' % (self.id))
            except:
                cron_available = False

            if cron_available:
                cron_available.write({'active': False})
        return True

    def button_connect(self):
        wcapi = self.wc_connect()
        wc_job = self.env['wc.process.job.cft'].create(
            {'wc_instance_id': self.id, 'message': 'Test Connection'})
        try:
            r = wcapi.get("orders", wc_job=wc_job)
        except Exception as e:
            raise Warning(e)
        if not isinstance(r, requests.models.Response):
            raise Warning(_("Response is not in proper format :: %s" % (r)))
        if r.status_code != 200:
            raise Warning(_("%s\n%s" % (r.status_code, r.reason)))
        else:
            self.write({'state': 'connect'})
            self.env['wc.order.status.cft'].import_order_status(self)
            self.env['wc.payment.gateway.cft'].get_payment_gateway(self)
        return True

    def import_basic_info(self):
        self.env['wc.order.status.cft'].import_order_status(self)
        self.env['wc.payment.gateway.cft'].get_payment_gateway(self)

    def button_confirm(self):
        self.write({'state': 'confirm'})

    def wc_connect(self):
        version = "wc/{0}".format(self.wc_version)
        return wc_api.api.API(url=self.website_url, consumer_key=self.consumer_key,
                              consumer_secret=self.consumer_secret, verify_ssl=self.verify_ssl, wp_api=True,
                              version=version, query_string_auth=True)

    def import_orders(self):
        return {
            'name': _("Import Orders"),
            'type': 'ir.actions.act_window',
            'res_model': 'wc.import.export.process.cft',
            'view_mode': 'form',
            'context': {'process_type': 'import_wc_orders'},
            'target': 'new'
        }

    def view_orders(self):
        return {
            'name': _("WooCommerce Orders"),
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order',
            'view_mode': 'tree,form',
            'domain': [('wc_instance_id', '=', self.id)],
        }

    def view_products(self):
        return {
            'name': _("WooCommerce Products"),
            'type': 'ir.actions.act_window',
            'res_model': 'wc.product.template.cft',
            'view_mode': 'tree,form',
            'domain': [('wc_instance_id', '=', self.id)],
        }

    def view_invoices(self):
        action = self.env.ref('woo_odoo_cft.action_invoice_wc_invoices').read()[0]
        action['domain'] = [('move_type', '=', 'out_invoice'), ('wc_instance_id', '!=', False),
                            ('wc_instance_id', '=', self.id)]
        return action

    def view_customers(self):
        action = self.env.ref('woo_odoo_cft.action_wc_partner_form').read()[0]
        action['domain'] = [('is_wc_customer', '=', True), ('customer_rank', '>', 0), ('parent_id', '=', False),
                            ('wc_instance_id', '=', self.id)]
        return action

    def view_coupons(self):
        action = self.env.ref('woo_odoo_cft.action_wc_coupons').read()[0]
        action['domain'] = [('wc_instance_id', '=', self.id)]
        return action

    def view_category(self):
        action = self.env.ref('woo_odoo_cft.product_categ_action').read()[0]
        action['domain'] = [('wc_instance_id', '=', self.id)]
        return action

    def view_delivery(self):
        action = self.env.ref('woo_odoo_cft.action_stock_picking_wc_cft').read()[0]
        action['domain'] = [('is_wc_delivery_order', '=', 'True'), ('wc_instance_id', '=', self.id)]
        return action

    def view_tags(self):
        action = self.env.ref('woo_odoo_cft.product_tags_action').read()[0]
        action['domain'] = [('wc_instance_id', '=', self.id)]
        return action

    def import_stock(self):
        return {
            'name': _("Import Stock"),
            'type': 'ir.actions.act_window',
            'res_model': 'wc.import.export.process.cft',
            'view_mode': 'form',
            'context': {'process_type': 'import_stock'},
            'target': 'new'
        }

    def update_wc_order_status(self):
        return {
            'name': _("Update Order Status"),
            'type': 'ir.actions.act_window',
            'res_model': 'wc.import.export.process.cft',
            'view_mode': 'form',
            'context': {'process_type': 'update_wc_order_status'},
            'target': 'new'
        }

    def import_wc_customers(self):
        return {
            'name': _("Sync Customers"),
            'type': 'ir.actions.act_window',
            'res_model': 'wc.import.export.process.cft',
            'view_mode': 'form',
            'context': {'process_type': 'import_wc_customers'},
            'target': 'new'
        }

    def import_wc_categs(self):
        return {
            'name': _("Sync Product Category"),
            'type': 'ir.actions.act_window',
            'res_model': 'wc.import.export.process.cft',
            'view_mode': 'form',
            'context': {'process_type': 'import_wc_categs'},
            'target': 'new'
        }

    def import_wc_tags(self):
        return {
            'name': _("Sync Product Tags"),
            'type': 'ir.actions.act_window',
            'res_model': 'wc.import.export.process.cft',
            'view_mode': 'form',
            'context': {'process_type': 'import_wc_tags'},
            'target': 'new'
        }

    def export_update_wc_coupons(self):
        return {
            'name': _("Export/Update Coupons"),
            'type': 'ir.actions.act_window',
            'res_model': 'wc.import.export.process.cft',
            'view_mode': 'form',
            'context': {'process_type': 'export_update_wc_coupons'},
            'target': 'new'
        }

    def export_wc_categs(self):
        return {
            'name': _("Export/Update Product Category"),
            'type': 'ir.actions.act_window',
            'res_model': 'wc.import.export.process.cft',
            'view_mode': 'form',
            'context': {'process_type': 'export_wc_categs'},
            'target': 'new'
        }

    def export_wc_tags(self):
        return {
            'name': _("Export/Update Product Tags"),
            'type': 'ir.actions.act_window',
            'res_model': 'wc.import.export.process.cft',
            'view_mode': 'form',
            'context': {'process_type': 'export_wc_tags'},
            'target': 'new'
        }

    def import_wc_products(self):
        return {
            'name': _("Sync Products"),
            'type': 'ir.actions.act_window',
            'res_model': 'wc.import.export.process.cft',
            'view_mode': 'form',
            'context': {'process_type': 'import_wc_products'},
            'target': 'new'
        }

    def export_wc_products(self):
        return {
            'name': _("Export/Update Products"),
            'type': 'ir.actions.act_window',
            'res_model': 'wc.import.export.process.cft',
            'view_mode': 'form',
            'context': {'process_type': 'export_wc_products'},
            'target': 'new'
        }

    def import_wc_coupons(self):
        return {
            'name': _("Sync Coupons"),
            'type': 'ir.actions.act_window',
            'res_model': 'wc.import.export.process.cft',
            'view_mode': 'form',
            'context': {'process_type': 'import_wc_coupons'},
            'target': 'new'
        }
