from odoo import models, fields, api


class ResPartner(models.Model):
    _inherit = "res.partner"

    is_wc_customer = fields.Boolean("Is WooCommerce Customer?")
    wc_instance_id = fields.Many2one("wc.instance.cft", "WooCommerce Instance")

    def create_or_update_wc_customer(self, vals, is_company=False, parent_id=False, type=False,
                                     wc_instance=False):
        country_obj = self.env['res.country']
        state_obj = self.env['res.country.state']

        first_name = vals.get('first_name')
        last_name = vals.get('last_name')

        if not first_name and not last_name and not is_company:
            return False

        city = vals.get('city')
        if is_company and vals.get('company'):
            name = vals.get('company')
        else:
            name = "%s %s" % (first_name, last_name)
        email = vals.get('email')
        phone = vals.get("phone")
        zip = vals.get('postcode')
        address1 = vals.get('address_1')
        address2 = vals.get('address_2')
        country_name = vals.get('country')
        state_name = vals.get('state')

        country = country_obj.search([('code', '=', country_name)], limit=1)
        if not country:
            country = country_obj.search([('name', '=', country_name)], limit=1)
        if not country:
            state = state_obj.search(["|", ('code', '=', state_name), ('name', '=', state_name)], limit=1)
        else:
            state = state_obj.search(
                ["|", ('code', '=', state_name), ('name', '=', state_name), ('country_id', '=', country.id)], limit=1)
        partner = False
        if is_company and not type:
            partner = email and self.search(
                ['|', ('email', '=', email), ('phone', '=', phone), ('is_company', '=', True)], limit=1) or False
        elif not type:
            partner = email and self.search(
                ['|', ('email', '=', email), ('phone', '=', phone), ('is_company', '=', False)], limit=1) or False
        if not partner and type:
            partner = self.search(
                [('name', '=', name), ('city', '=', city), ('street', '=', address1), ('street2', '=', address2),
                 ('zip', '=', zip), ('country_id', '=', country.id),
                 ('state_id', '=', state.id)], limit=1)
        if partner and not type:
            partner.with_context(res_partner_search_mode='customer').write(
                {'state_id': state and state.id or False, 'is_company': is_company,
                 'phone': phone or partner.phone,
                 'is_wc_customer': True,
                 'lang': wc_instance.lang_id.code,
                 'property_product_pricelist': wc_instance.pricelist_id.id,
                 'property_account_position_id': wc_instance.fiscal_position_id and wc_instance.fiscal_position_id.id or False,
                 'property_payment_term_id': wc_instance.payment_term_id and wc_instance.payment_term_id.id or False,
                 'email': email or False, 'wc_instance_id': wc_instance.id})
        elif not partner:
            partner = self.with_context(res_partner_search_mode='customer').create(
                {'type': type, 'parent_id': parent_id, 'is_wc_customer': True,
                 'name': name, 'state_id': state and state.id or False, 'city': city,
                 'street': address1, 'street2': address2,
                 'phone': phone, 'zip': zip, 'email': email,
                 'country_id': country and country.id or False, 'is_company': is_company,
                 'lang': wc_instance.lang_id.code, 'wc_instance_id': wc_instance.id,
                 'property_product_pricelist': wc_instance.pricelist_id.id,
                 'property_account_position_id': wc_instance.fiscal_position_id and wc_instance.fiscal_position_id.id or False,
                 'property_payment_term_id': wc_instance.payment_term_id and wc_instance.payment_term_id.id or False,
                 })
        return partner

    @api.model
    def import_wc_customers(self, wc_instance=False):
        if not wc_instance:
            return False
        wcapi = wc_instance.wc_connect()
        wc_job = self.env['wc.process.job.cft'].create(
            {'wc_instance_id': wc_instance.id, 'process_type': 'customer', 'operation_type': 'import_sync',
             'message': 'Process for Import/Sync Customers'})
        response = wcapi.get('customers?per_page=100', wc_job=wc_job)
        wc_customers = []
        customer_response = response.json()
        wc_customers = wc_customers + customer_response
        total_pages = response.headers.get('X-WP-TotalPages')
        if int(total_pages) >= 2:
            for page in range(2, int(total_pages) + 1):
                page_res = wcapi.get('customers?per_page=100&page=%s' % (page), wc_job=wc_job)
                if page_res:
                    wc_customers = wc_customers + page_res.json()
        for customer in wc_customers:
            partner = False
            billing_addr = customer.get('billing', False)
            shipping_addr = customer.get('shipping', False)
            company_id = False
            if billing_addr:
                if billing_addr.get('company'):
                    company_id = self.create_or_update_wc_customer(billing_addr, True, False, False,
                                                                   wc_instance)
                partner = self.create_or_update_wc_customer(billing_addr, False,
                                                            company_id and company_id.id or False, False,
                                                            wc_instance)
            if partner and shipping_addr:
                self.create_or_update_wc_customer(shipping_addr, False, company_id and company_id.id or partner.id,
                                                  'delivery',
                                                  wc_instance)
