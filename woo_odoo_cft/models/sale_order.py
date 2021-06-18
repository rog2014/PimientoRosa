from odoo import models, fields, api, _
from odoo.exceptions import Warning
from datetime import datetime


class SaleOrder(models.Model):
    _inherit = "sale.order"

    # def delivery_set(self):
    #     if self.wc_order_id:
    #         raise Warning(_('You are not allow to change manually shipping charge in WooCommerce order.'))
    #     else:
    #         super(SaleOrder, self).delivery_set()


    def _get_wc_order_status(self):
        for order in self:
            flag = False
            for picking in order.picking_ids:
                if picking.state != 'cancel':
                    flag = True
                    break
            if not flag:
                order.updated_in_wc = False
                continue
            if order.picking_ids:
                order.updated_in_wc = True
            else:
                order.updated_in_wc = False
            for picking in order.picking_ids:
                if picking.state == 'cancel':
                    continue
                if picking.picking_type_id.code != 'outgoing':
                    continue
                if not picking.updated_in_wc:
                    order.updated_in_wc = False
                    break

    def _search_wc_order_ids(self, operator, value):
        query = """select sale_order.id from stock_picking
                inner join sale_order on sale_order.procurement_group_id=stock_picking.group_id
                inner join stock_picking_type on stock_picking.picking_type_id=stock_picking_type.id
                inner join stock_location on stock_location.id=stock_picking_type.default_location_dest_id and stock_location.usage='customer'
                where stock_picking.updated_in_wc=False and stock_picking.state='done'"""
        self._cr.execute(query)
        results = self._cr.fetchall()
        order_ids = []
        for result_tuple in results:
            order_ids.append(result_tuple[0])
        order_ids = list(set(order_ids))
        return [('id', 'in', order_ids)]

    wc_order_id = fields.Char("Order Reference", help="WooCommerce Order Reference")
    wc_order_number = fields.Char("Order Number", help="WooCommerce Order Number")
    updated_in_wc = fields.Boolean("Updated In WooCommerce", compute='_get_wc_order_status',
                                   search='_search_wc_order_ids')
    wc_instance_id = fields.Many2one("wc.instance.cft", "WooCommerce Instance")
    wc_payment_gateway_id = fields.Many2one("wc.payment.gateway.cft", "Payment Gateway")
    wc_trans_id = fields.Char("Transaction Id", help="WooCommerce Order Transaction Id")
    canceled_in_wc = fields.Boolean("Canceled In WooCommerce", default=False)
    order_status = fields.Many2one('wc.order.status.cft')

    def cancel_so_in_wc(self):
        view = self.env.ref('woo_odoo_cft.view_wc_cancel_order_wizard')
        return {
            'name': _('Cancel Order In WooCommerce'),
            'type': 'ir.actions.act_window',
            'view_mode': 'form',
            'res_model': 'wc.cancel.order.wizard',
            'views': [(view.id, 'form')],
            'view_id': view.id,
            'target': 'new',
            'context': self._context
        }

    @api.model
    def create_wc_tax(self, value, price_included, company, title, wc_instance):
        account_tax_obj = self.env['account.tax']
        name = '%s %s (%s)' % (title, str(value) + '%', wc_instance.name)
        accounttax_id = account_tax_obj.create(
            {'name': name, 'amount': float(value), 'type_tax_use': 'sale', 'price_include': price_included,
             'company_id': company.id})
        return accounttax_id

    @api.model
    def get_wc_odoo_tax_ids(self, wc_instance, tax_datas, tax_included, wc_job):
        tax_id = []
        taxes = []
        for tax in tax_datas:
            rate = float(tax.get('rate', 0.0))
            if rate != 0.0:
                acctax_id = self.env['account.tax'].search(
                    [('price_include', '=', tax_included), ('type_tax_use', '=', 'sale'), ('amount', '=', rate),
                     ('company_id', '=', wc_instance.warehouse_id.company_id.id)], limit=1)
                if not acctax_id:
                    acctax_id = self.create_wc_tax(rate, tax_included, wc_instance.warehouse_id.company_id,
                                                   tax.get('name') + "_%s" % (
                                                       "Included" if tax_included else "Excluded"), wc_instance)
                    if acctax_id:
                        message = """%s tax created with %s rate for Company %s""" % (
                            acctax_id.name, rate, wc_instance.company_id.name)
                        wc_job.env['wc.process.job.cft.line'].create(
                            {'wc_job_id': wc_job.id, 'message': message})
                if acctax_id:
                    taxes.append(acctax_id.id)
        if taxes:
            tax_id = [(6, 0, taxes)]
        return tax_id

    @api.model
    def check_wc_order_line_product(self, lines, wc_instance, order_number, wc_job):
        odoo_product_obj = self.env['product.product']
        wc_product_obj = self.env['wc.product.product.cft']
        wc_product_template_obj = self.env['wc.product.template.cft']
        for line in lines:
            line_product_id = line.get('product_id', False) or line.get('variation_id', False)
            odoo_product = False
            sku = line.get('sku') or ''
            wc_variant = line_product_id and wc_product_obj.search(
                [('variant_id', '=', line_product_id), ('wc_instance_id', '=', wc_instance.id)], limit=1)
            if not wc_variant:
                wc_variant = sku and wc_product_obj.search(
                    [('default_code', '=', sku), ('wc_instance_id', '=', wc_instance.id)], limit=1)
            if not wc_variant:
                odoo_product = sku and odoo_product_obj.search([('default_code', '=', sku)], limit=1)

            if not odoo_product and not wc_variant:
                wc_instance.auto_create_product and wc_product_template_obj.with_context(
                    from_so=True).import_wc_products(wc_instance,
                                                     line_product_id, update_template=False)
                odoo_product = odoo_product_obj.search([('default_code', '=', sku)], limit=1)

            if not wc_variant and not odoo_product:
                wc_job.env['wc.process.job.cft.line'].create(
                    {'wc_job_id': wc_job.id, 'message': "%s SKU Product Not found for order %s" % (sku, order_number)})
                return False
        return True

    @api.model
    def create_wc_sale_order_line(self, line, tax_ids, product, quantity, fiscal_position, name, order, price,
                                  is_shipping=False):
        sale_order_line_obj = self.env['sale.order.line']
        uom_id = product and product.uom_id and product.uom_id.id or False
        product_data = {
            'product_id': product and product.ids[0] or False,
            'order_id': order.id,
            'company_id': order.company_id.id,
            'product_uom': uom_id,
            'name': name,
        }
        tmp_sale_line = sale_order_line_obj.new(product_data)
        tmp_sale_line.product_id_change()
        so_line_vals = sale_order_line_obj._convert_to_write(
            {name: tmp_sale_line[name] for name in tmp_sale_line._cache})
        if tax_ids:
            tax_ids = tax_ids and self.env['account.tax'].search([('id', 'in', tax_ids[0][2])])
        if fiscal_position:
            tax_ids = fiscal_position.map_tax(tax_ids, product[0], order.partner_id) if fiscal_position else tax_ids
        so_line_vals.update(
            {
                'order_id': order.id,
                'product_uom_qty': quantity,
                'price_unit': price,
                'wc_line_id': line.get('id'),
                'is_delivery': is_shipping,
                'tax_id': tax_ids and [(6, 0, tax_ids.ids)] or [(6, 0, [])],
            }
        )
        line = sale_order_line_obj.create(so_line_vals)
        return line

    @api.model
    def search_wc_product(self, line, wc_instance):
        wc_product_obj = self.env['wc.product.product.cft']
        odoo_product_obj = self.env['product.product']
        variant_id = line.get('product_id')
        sku = line.get('sku')
        wc_product = wc_product_obj.search(
            [('wc_instance_id', '=', wc_instance.id), ('variant_id', '=', variant_id)], limit=1)
        if wc_product:
            return wc_product.product_id
        wc_product = wc_product_obj.search(
            [('wc_instance_id', '=', wc_instance.id), ('default_code', '=', sku)], limit=1)
        wc_product and wc_product.write({'variant_id': variant_id})
        if wc_product:
            return wc_product.product_id
        odoo_product = sku and odoo_product_obj.search([('default_code', '=', sku)], limit=1)
        if odoo_product:
            return odoo_product
        return False

    def create_or_update_wc_payment_gateway(self, wc_instance, result):
        wc_payment_gateway_obj = self.env["wc.payment.gateway.cft"]
        code = result.get("payment_method")
        name = result.get("payment_method_title")
        if not code:
            return False
        wc_payment_gateway = wc_payment_gateway_obj.search(
            [("code", "=", code), ("wc_instance_id", "=", wc_instance.id)],
            limit=1)
        if wc_payment_gateway:
            vals = {"name": name}
            wc_payment_gateway.write(vals)
        else:
            vals = {"code": code, "name": name, "wc_instance_id": wc_instance.id}
            wc_payment_gateway = wc_payment_gateway_obj.create(vals)
        return wc_payment_gateway

    @api.model
    def get_wc_order_vals(self, result, workflow, invoice_address, wc_instance, partner, shipping_address, pricelist_id,
                          fiscal_position, payment_term, wc_payment_gateway):
        wc_order_number = result.get('number')
        note = result.get('customer_note')
        created_at = result.get('date_created').replace("T", " ")
        wc_trans_id = result.get("transaction_id")

        if wc_instance.wc_order_prefix:
            name = "%s%s" % (wc_instance.wc_order_prefix, wc_order_number)
        else:
            name = wc_order_number

        ordervals = {
            'name': name,
            'partner_invoice_id': invoice_address.ids[0],
            'date_order': created_at.replace("T", " "),
            'warehouse_id': wc_instance.warehouse_id.id,
            'partner_id': partner.ids[0],
            'partner_shipping_id': shipping_address.ids[0],
            'state': 'draft',
            'pricelist_id': pricelist_id or wc_instance.pricelist_id.id or False,
            'fiscal_position_id': fiscal_position and fiscal_position.id or False,
            'payment_term_id': payment_term or wc_instance.payment_term_id.id or False,
            'note': note,
            'wc_order_id': result.get('id'),
            'wc_order_number': wc_order_number,
            'wc_instance_id': wc_instance.id,
            'team_id': wc_instance.team_id and wc_instance.team_id.id or False,
            'company_id': wc_instance.company_id.id,
            'wc_payment_gateway_id': wc_payment_gateway and wc_payment_gateway.id or False,
            'wc_trans_id': wc_trans_id,
        }

        if workflow:
            ordervals.update({
                'picking_policy': workflow.picking_policy,
                'auto_workflow_process_id': workflow.id,
                'invoice_policy': workflow.invoice_policy
            })
        return ordervals

    @api.model
    def import_wc_orders(self, wc_instance=False):
        instances = []
        wc_job = self.env['wc.process.job.cft'].create(
            {'wc_instance_id': wc_instance.id, 'process_type': 'order', 'operation_type': 'import',
             'message': 'Process for Import Order'})
        if not wc_instance:
            instances = self.env['wc.instance.cft'].search(
                [('so_auto_import', '=', True), ('state', '=', 'confirm')])
        else:
            instances.append(wc_instance)
        for wc_instance in instances:
            wcapi = wc_instance.wc_connect()
            order_ids = []
            for order_status in wc_instance.import_order_status_ids:
                response = wcapi.get('orders?status=%s&per_page=100&after=%s' % (
                    order_status.status, wc_instance.import_order_after.isoformat()), wc_job=wc_job)
                if not response:
                    return False
                order_ids = order_ids + response.json()
                total_pages = response.headers.get('x-wp-totalpages')
                if int(total_pages) >= 2:
                    for page in range(2, int(total_pages) + 1):
                        page_res = wcapi.get('orders?status=%s&per_page=100&after=%s&page=%s' % (
                            order_status.status, wc_instance.import_order_after.isoformat(), page), wc_job=wc_job)
                        if page_res:
                            order_ids = order_ids + page_res.json()

            for order in order_ids:
                tax_included = order.get('prices_include_tax')
                if self.search([('wc_instance_id', '=', wc_instance.id), ('wc_order_id', '=', order.get('id')),
                                ('wc_order_number', '=', order.get('number'))]):
                    continue
                lines = order.get('line_items')
                if not self.check_wc_order_line_product(lines, wc_instance, order.get('number'), wc_job):
                    continue
                wc_payment_gateway = self.create_or_update_wc_payment_gateway(wc_instance, order)
                if not wc_payment_gateway:
                    wc_job.env['wc.process.job.cft.line'].create(
                        {'wc_job_id': wc_job.id,
                         'message': "Payment Gateway not available in order %s" % (order.get('number'))})
                workflow = False
                company_id = False
                if order.get('billing', False):
                    if order.get('billing').get('company'):
                        company_id = self.env['res.partner'].create_or_update_wc_customer(order.get('billing', False),
                                                                                          True,
                                                                                          False, False,
                                                                                          wc_instance)
                    partner = self.env['res.partner'].create_or_update_wc_customer(order.get('billing', False), False,
                                                                                   company_id and company_id.id or False,
                                                                                   False,
                                                                                   wc_instance)
                if not partner:
                    message = "Customer Not Available In %s Order" % (order.get('number'))
                    wc_job.env['wc.process.job.cft.line'].create(
                        {'wc_job_id': wc_job.id, 'message': message})
                    continue
                shipping_address = order.get('shipping', False) and self.env[
                    'res.partner'].create_or_update_wc_customer(order.get(
                    'shipping'), False, company_id and company_id.id or partner.id, 'delivery', wc_instance) or partner
                temp_so = self.new({'partner_id': partner.id})
                temp_so.onchange_partner_id()
                temp_so_vals = self._convert_to_write({name: temp_so[name] for name in temp_so._cache})
                temp_so = self.new(temp_so_vals)
                temp_so.onchange_partner_shipping_id()
                temp_so_vals = self._convert_to_write({name: temp_so[name] for name in temp_so._cache})

                fiscal_position = partner.property_account_position_id
                pricelist_id = temp_so_vals.get('pricelist_id', False)
                payment_term = temp_so_vals.get('payment_term_id', False)
                wc_order_vals = self.get_wc_order_vals(order, workflow, partner, wc_instance, partner, shipping_address,
                                                       pricelist_id, fiscal_position, payment_term, wc_payment_gateway)
                wc_order_status = self.env['wc.order.status.cft'].search(
                    [('status', '=', order.get('status')), ('wc_instance_id', '=', wc_instance.id)], limit=1)
                wc_order_vals and wc_order_vals.update({'order_status': wc_order_status.id})
                sale_order = self.create(wc_order_vals) if wc_order_vals else False

                if not sale_order:
                    continue
                if tax_included:
                    total_discount = float(order.get('discount_total', 0.0)) + float(order.get('discount_tax', 0.0))
                if not tax_included:
                    total_discount = float(order.get('discount_total', 0.0))

                shipping_taxable = False
                tax_datas = []
                for tax_line in order.get('tax_lines'):
                    rate_id = tax_line.get('rate_id')
                    if rate_id:
                        tax_wc_job = self.env['wc.process.job.cft'].create(
                            {'wc_instance_id': wc_instance.id, 'process_type': 'tax', 'operation_type': 'import',
                             'message': 'Process for Import Order Tax'})
                        res_rate = wcapi.get('taxes/%s' % (rate_id), wc_job=tax_wc_job)
                        if not res_rate:
                            continue
                        rate = res_rate.json()
                        tax_datas.append(rate)
                        shipping_taxable = rate.get('shipping')
                tax_ids = self.get_wc_odoo_tax_ids(wc_instance, tax_datas, tax_included, wc_job=wc_job)
                for line in lines:
                    product = self.search_wc_product(line, wc_instance)
                    if not product:
                        continue
                    if tax_included:
                        unit_price = (float(line.get('subtotal_tax')) + float(line.get('subtotal'))) / float(
                            line.get('quantity'))
                    else:
                        unit_price = float(line.get('subtotal')) / float(line.get('quantity'))
                    taxes = []
                    for tax in line.get('taxes'):
                        tax_wc_job = self.env['wc.process.job.cft'].create(
                            {'wc_instance_id': wc_instance.id, 'process_type': 'tax', 'operation_type': 'import',
                             'message': 'Process for Import Order Tax'})
                        res_rate = wcapi.get('taxes/%s' % (tax.get('id')), wc_job=tax_wc_job)
                        if not res_rate:
                            continue
                        rate = res_rate.json()
                        tax_rate = float(rate.get('rate', 0.0))
                        account_tax = self.env['account.tax'].search(
                            [('price_include', '=', tax_included), ('type_tax_use', '=', 'sale'),
                             ('amount', '=', tax_rate), ('company_id', '=', wc_instance.warehouse_id.company_id.id)],
                            limit=1)
                        account_tax and taxes.append(account_tax.id)
                    self.create_wc_sale_order_line(line, [(6, 0, taxes)], product, line.get('quantity'),
                                                   fiscal_position, product.name, sale_order, unit_price, False)

                product_template_obj = self.env['product.template']
                for line in order.get('shipping_lines', []):
                    if shipping_taxable and float(order.get('shipping_tax')) > 0.0:
                        shipping_tax_ids = self.get_wc_odoo_tax_ids(wc_instance, tax_datas, False, wc_job=wc_job)
                    else:
                        shipping_tax_ids = []
                    delivery_method = line.get('method_title')
                    if delivery_method:
                        carrier = self.env['delivery.carrier'].search([('wc_code', '=', delivery_method)], limit=1)
                        if not carrier:
                            carrier = self.env['delivery.carrier'].search([('name', '=', delivery_method)], limit=1)
                        if not carrier:
                            carrier = self.env['delivery.carrier'].search(
                                ['|', ('name', 'ilike', delivery_method), ('wc_code', 'ilike', delivery_method)],
                                limit=1)
                        if not carrier:
                            product_template = product_template_obj.search(
                                [('name', '=', delivery_method), ('type', '=', 'service')], limit=1)
                            if not product_template:
                                product_template = product_template_obj.create(
                                    {'name': delivery_method, 'type': 'service'})
                            carrier = self.env['delivery.carrier'].create(
                                {'name': delivery_method, 'wc_code': delivery_method, 'fixed_price': line.get('total'),
                                 'product_id': product_template.product_variant_ids[0].id})
                        sale_order.write({'carrier_id': carrier.id})
                        if carrier.product_id:
                            shipping_product = carrier.product_id
                    self.create_wc_sale_order_line(line, shipping_tax_ids, shipping_product, 1, fiscal_position,
                                                   shipping_product and shipping_product.name or line.get(
                                                       'method_title'), sale_order, line.get('total'), True)
                if total_discount > 0.0:
                    self.create_wc_sale_order_line({}, tax_ids, wc_instance.discount_line_product_id, 1,
                                                   fiscal_position,
                                                   wc_instance.discount_line_product_id.name, sale_order,
                                                   total_discount * -1,
                                                   False)

                fee_lines = order.get("fee_lines", [])
                for fee_line in fee_lines:
                    fee_value = fee_line.get("total")
                    fee = fee_line.get("name")
                    fee_line_tax_ids = self.get_wc_odoo_tax_ids(wc_instance, tax_datas, False, wc_job=wc_job)
                    if fee_value:
                        self.create_wc_sale_order_line({}, fee_line_tax_ids, wc_instance.fee_line_product_id, 1,
                                                       fiscal_position, fee, sale_order, fee_value, False)
                self.env['wc.order.status.cft'].process_order_autoworkflow(sale_order, wc_job)
            wc_instance.update({'import_order_after': datetime.now()})
        return True

    @api.model
    def auto_update_wc_order_status(self, ctx={}):
        wc_instance_obj = self.env['wc.instance.cft']
        if not isinstance(ctx, dict) or not 'wc_instance_id' in ctx:
            return True
        wc_instance_id = ctx.get('wc_instance_id', False)
        wc_instance = wc_instance_id and wc_instance_obj.search(
            [('id', '=', wc_instance_id), ('state', '=', 'confirm')]) or False
        if wc_instance:
            self.update_wc_order_status(wc_instance)
            # wc_instance.so_update_next_execution = wc_instance.so_update_cron_id.nextcall
        return True

    @api.model
    def auto_import_wc_sale_order(self, ctx={}):
        wc_instance_obj = self.env['wc.instance.cft']
        if not isinstance(ctx, dict) or not 'wc_instance_id' in ctx:
            return True
        wc_instance_id = ctx.get('wc_instance_id', False)
        wc_instance = wc_instance_id and wc_instance_obj.search(
            [('id', '=', wc_instance_id), ('state', '=', 'confirm')]) or False
        if wc_instance:
            self.import_wc_orders(wc_instance)
            # wc_instance.so_import_next_execution = wc_instance.so_import_cron_id.nextcall
        return True

    @api.model
    def update_wc_order_status(self, wc_instance):
        instances = []
        if not wc_instance:
            instances = self.env['wc.instance.cft'].search(
                [('order_auto_update', '=', True), ('state', '=', 'confirm')])
        else:
            instances.append(wc_instance)
        for wc_instance in instances:
            wc_job = self.env['wc.process.job.cft'].create(
                {'wc_instance_id': wc_instance.id, 'process_type': 'order', 'operation_type': 'update',
                 'message': 'Process for Update Order Status'})
            wcapi = wc_instance.wc_connect()
            sales_orders = self.search(
                [('warehouse_id', '=', wc_instance.warehouse_id.id), ('wc_order_id', '!=', False),
                 ('wc_instance_id', '=', wc_instance.id), ('updated_in_wc', '=', False)],
                order='date_order')
            for sale_order in sales_orders:
                for picking in sale_order.picking_ids:
                    if picking.updated_in_wc or picking.state != 'done' or picking.picking_type_code != 'outgoing':
                        continue
                    info = {"status": "completed"}
                    info.update({"id": sale_order.wc_order_id})
                    response = wcapi.post('orders/batch', {'update': [info]}, wc_job=wc_job)
                    if response:
                        picking.write({'updated_in_wc': True})
        return True

    def _prepare_invoice(self):
        invoice = super(SaleOrder, self)._prepare_invoice()
        if invoice and self.wc_instance_id:
            invoice.update({'wc_instance_id': self.wc_instance_id.id})
        return invoice


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    wc_line_id = fields.Char("WooCommerce Line Id")
