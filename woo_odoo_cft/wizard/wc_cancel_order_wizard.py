from odoo import models, fields, api


class wc_cancel_order_wizard(models.TransientModel):
    _name = "wc.cancel.order.wizard"
    _description = "WooCommerce Cancel Order"

    message = fields.Char("Reason")
    amount = fields.Float("Amount", digits=(12, 2))
    suggested_amount = fields.Float("Suggest Amount", digits=(12, 2))
    journal_id = fields.Many2one('account.journal', 'Journal',
                                 help='You can select here the journal to use for the credit note that will be created. If you leave that field empty, it will use the same journal as the current invoice.')
    inv_line_des = fields.Char("Invoice Line Description", default="Refund Line")
    auto_create_refund = fields.Boolean("Auto Create Refund", default=False)
    company_id = fields.Many2one("res.company")
    date = fields.Date("Invoice Date")

    @api.model
    def default_get(self, fields):
        res = super(wc_cancel_order_wizard, self).default_get(fields)
        active_id = self._context.get('active_id')
        so = self.env['sale.order'].browse(active_id)
        if so.invoice_ids:
            total = 0
            for invoice in so.invoice_ids:
                total += invoice.amount_total if invoice.state == 'posted' else 0
            res.update({'suggested_amount': total, 'amount': total, 'company_id': so.company_id.id})
        return res

    
    def cancel_so_in_wc(self):
        active_id = self._context.get('active_id')
        so = self.env['sale.order'].browse(active_id)
        wc_instance = so.wc_instance_id
        wc_job = self.env['wc.process.job.cft'].create(
            {'wc_instance_id': wc_instance.id, 'process_type': 'order', 'operation_type': 'update',
             'message': 'Process for Cancel Order'})
        wcapi = wc_instance.wc_connect()
        info = {'status': 'cancelled'}
        info.update({'id': so.wc_order_id})
        response = wcapi.post('orders/batch', {'update': [info]}, wc_job=wc_job)
        if not response:
            return False
        if self.auto_create_refund:
            self.create_refund(so)
        so.write({'canceled_in_wc': True})
        return True

    
    def create_refund(self, order):
        account_invoice_line_obj = self.env['account.move.line']
        journal_id = self.journal_id and self.journal_id.id
        description = self.message or order.name
        invoice_id = False
        for line in order.order_line:
            for invoice_line in line.invoice_lines:
                invoice_id = invoice_line.invoice_id
                break
        invoice_vals = {
            'name': description,
            'origin': order.name,
            'move_type': 'out_refund',
            'reference': order.client_order_ref or order.name,
            'account_id': order.partner_id.property_account_receivable_id.id,
            'partner_id': order.partner_invoice_id.id,
            'journal_id': journal_id,
            'currency_id': order.pricelist_id.currency_id.id,
            'comment': order.note,
            'wc_instance_id': order.wc_instance_id.id,
            'payment_term_id': order.payment_term_id and order.payment_term_id.id or False,
            'fiscal_position_id': order.fiscal_position_id.id or order.partner_id.property_account_position_id.id,
            'company_id': self.company_id.id,
            'user_id': self._uid or False,
            'date': self.date or False,
            'team_id': order.team_id and order.team_id.id,
            'invoice_id': invoice_id and invoice_id.id or False,
        }
        invoice = self.env['account.move'].create(invoice_vals)
        tax_ids = []
        product = False
        qty = 0.0
        for line in order.order_line:
            if not product:
                product = line.product_id
            tax_ids += line.tax_id.ids
            qty += line.qty_invoiced
        tax_ids = list(set(tax_ids))
        account_id = product.property_account_income_id.id or product.categ_id.property_account_income_categ_id.id
        price_unit = round(self.amount / qty, self.env['decimal.precision'].precision_get('Product Price'))
        vals = ({'invoice_line_tax_ids': [(6, 0, tax_ids)], 'invoice_id': invoice.id, 'product_id': False,
                 'price_unit': price_unit, 'quantity': qty, 'name': self.inv_line_des, 'account_id': account_id})
        account_invoice_line_obj.create(vals)
        return True
