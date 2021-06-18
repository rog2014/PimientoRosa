from odoo import models, fields, api


class WcPaymentGateway(models.Model):
    _name = "wc.payment.gateway.cft"
    _description = "WooCommerce Payment Gateway"

    name = fields.Char("Payment Method", required=True)
    code = fields.Char("Payment Code", required=True,
                       help="The payment code should match Gateway ID in your WooCommerce Checkout Settings.")
    wc_instance_id = fields.Many2one("wc.instance.cft", "Instance", required=True, ondelete='cascade')
    journal_id = fields.Many2one('account.journal', 'Payment Journal', domain=[('type', 'in', ['cash', 'bank'])])
    _sql_constraints = [('_payment_gateway_unique_constraint', 'unique(code,wc_instance_id)',
                         "Payment gateway code must be unique in the list")]

    def get_payment_gateway(self, wc_instance):
        if not wc_instance:
            return False
        wcapi = wc_instance.wc_connect()
        wc_job = self.env['wc.process.job.cft'].create(
            {'wc_instance_id': wc_instance.id, 'process_type': 'payment_gateway', 'operation_type': 'import',
             'message': 'Process for Import Payment Gateway'})
        res = wcapi.get("payment_gateways", wc_job=wc_job)
        if not res:
            return False
        for payment_method in res.json():
            if payment_method.get('enabled'):
                code = payment_method.get('id')
                if self.search([('code', '=', code), ('wc_instance_id', '=', wc_instance.id)]):
                    continue
                name = payment_method.get('title')
                self.create({'name': name, 'code': code, 'wc_instance_id': wc_instance.id})
        return True
